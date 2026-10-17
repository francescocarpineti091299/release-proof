param(
    [string]$StateFile = (Join-Path $HOME '.releaseproof-azure/releaseproof.json'),
    [string]$EnvFile = (Join-Path $PSScriptRoot '../../.env'),
    [string]$Commit = 'HEAD'
)
$ErrorActionPreference = 'Stop'
$state = Get-Content -Raw $StateFile | ConvertFrom-Json
if (-not (Test-Path $EnvFile)) { throw 'AMD environment file is required; do not commit it' }
$repo = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$sha = (& git -C $repo rev-parse "$Commit^{commit}").Trim()
if ($LASTEXITCODE -ne 0 -or $sha -notmatch '^[0-9a-f]{40}$') { throw 'Invalid release commit' }
$target = "ubuntu@$($state.public_ip)"
$sshOptions = @('-i', $state.key_file, '-o', 'StrictHostKeyChecking=accept-new',
    '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15', '-o', 'ServerAliveInterval=30')
function Invoke-Remote([string]$Command) {
    # Send shell commands through Python stdin: Windows PowerShell otherwise strips
    # nested quotes passed to ssh.exe. The payload contains no secret env contents.
    $payload = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($Command))
    $python = "import base64,subprocess,sys; sys.exit(subprocess.call(base64.b64decode('$payload').decode(),shell=True))"
    $python | & ssh @sshOptions $target 'python3 -'
    if ($LASTEXITCODE -ne 0) { throw 'Remote release command failed' }
}
Invoke-Remote 'cloud-init status --wait && test -f /var/lib/releaseproof-bootstrap-done && docker compose version'
# Refuse to interrupt jobs on an existing deployment; no forced process stop.
$activeCheck = @'
if docker ps --format '{{.Names}}' | grep -qx releaseproof-api-1; then
  docker exec releaseproof-api-1 python -c 'import json,urllib.request; runs=json.load(urllib.request.urlopen("http://localhost:8000/api/assessments?limit=200")); assert not any(r["status"] in ["RUNNING","QUEUED"] for r in runs), "Wait for active assessments"'
fi
'@
Invoke-Remote $activeCheck
$release = "/opt/releaseproof/releases/$sha"
$temp = Join-Path $env:LOCALAPPDATA ('Temp/opencode/releaseproof-azure-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temp | Out-Null
$archive = Join-Path $temp 'release.tar.gz'
$runtimeEnv = Join-Path $temp '.env'
try {
    & git -C $repo archive --format=tar.gz "--output=$archive" $sha
    if ($LASTEXITCODE -ne 0) { throw 'Release archive failed' }
    $overrides = @('SITE_ADDRESS', 'AZURE_FRONT_DOOR_ID', 'RELEASEPROOF_ENV',
        'RELEASEPROOF_EXPOSE_EXPERIMENTAL', 'RELEASEPROOF_MAX_ACTIVE_RUNS', 'RELEASEPROOF_MUTATION_RPM')
    $lines = Get-Content $EnvFile | Where-Object {
        $name = ($_ -split '=', 2)[0].Trim()
        $name -notin $overrides
    }
    $lines += @("SITE_ADDRESS=$($state.origin_host)", "AZURE_FRONT_DOOR_ID=$($state.frontdoor_id)",
        'RELEASEPROOF_ENV=demo', 'RELEASEPROOF_EXPOSE_EXPERIMENTAL=0',
        'RELEASEPROOF_MAX_ACTIVE_RUNS=4', 'RELEASEPROOF_MUTATION_RPM=20')
    [IO.File]::WriteAllText($runtimeEnv, ($lines -join "`n") + "`n", [Text.UTF8Encoding]::new($false))
    Invoke-Remote "install -d -m 0755 $release"
    & scp @sshOptions -q $archive "${target}:/home/ubuntu/releaseproof-$sha.tar.gz"
    if ($LASTEXITCODE -ne 0) { throw 'Archive upload failed' }
    Invoke-Remote "tar -xzf /home/ubuntu/releaseproof-$sha.tar.gz -C $release && rm /home/ubuntu/releaseproof-$sha.tar.gz"
    & scp @sshOptions -q $runtimeEnv "${target}:$release/.env"
    if ($LASTEXITCODE -ne 0) { throw 'Secret environment upload failed' }
    Invoke-Remote "chmod 600 $release/.env && cd $release && docker compose -f docker-compose.yml -f docker-compose.public.yml -f docker-compose.azure.yml up -d --build && ln -sfn $release /opt/releaseproof/current && docker compose ps"
    Write-Output "Deployed release $sha; verify $($state.viewer_url) before submission"
}
finally {
    if (Test-Path $runtimeEnv) { Remove-Item -LiteralPath $runtimeEnv -Force }
    if (Test-Path $archive) { Remove-Item -LiteralPath $archive -Force }
    if (Test-Path $temp) { Remove-Item -LiteralPath $temp }
}
