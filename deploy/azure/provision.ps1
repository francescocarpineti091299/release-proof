param(
    [Parameter(Mandatory = $true)][string]$SubscriptionId,
    [string]$ResourceGroup = 'rg-releaseproof-demo-weu',
    [string]$Location = 'westeurope',
    [string]$VmSize = 'Standard_D8as_v4',
    [string]$StateDirectory = (Join-Path $HOME '.releaseproof-azure')
)
$ErrorActionPreference = 'Stop'

function Invoke-AzJson([string[]]$Arguments) {
    $result = & az @Arguments --subscription $SubscriptionId --only-show-errors --output json
    if ($LASTEXITCODE -ne 0) { throw "Azure command failed: $($Arguments[0..1] -join ' ')" }
    if ($result) { return ($result -join "`n" | ConvertFrom-Json) }
}

$existing = Invoke-AzJson @('group', 'list', '--query', "[?name=='$ResourceGroup']")
if ($existing -and $existing[0].tags.app -ne 'releaseproof') {
    throw 'Refusing to use a resource group not owned by ReleaseProof'
}
New-Item -ItemType Directory -Force -Path $StateDirectory | Out-Null
$key = Join-Path $StateDirectory 'releaseproof'
if (-not (Test-Path $key)) {
    & python -c "import subprocess,sys; subprocess.run(['ssh-keygen','-t','ed25519','-N','','-f',sys.argv[1]],check=True,capture_output=True)" $key
    if ($LASTEXITCODE -ne 0) { throw 'SSH key generation failed' }
}
if (-not (Test-Path "$key.pub")) { throw 'Existing SSH key has no public-key counterpart' }
$suffix = $SubscriptionId.Replace('-', '').Substring(0, 8)
$dnsName = "releaseproof-$suffix"
$vmName = 'releaseproof-vm'
$nsgName = 'releaseproof-nsg'
$frontDoorProfile = 'releaseproof-frontdoor'
$endpointName = "releaseproof-$suffix"
$operatorIp = (Invoke-RestMethod 'https://checkip.amazonaws.com').Trim()
if ($operatorIp -notmatch '^\d{1,3}(\.\d{1,3}){3}$') { throw 'Invalid operator IPv4 address' }

Invoke-AzJson @('group', 'create', '--name', $ResourceGroup, '--location', $Location,
    '--tags', 'app=releaseproof', 'purpose=public-judging-demo') | Out-Null
Invoke-AzJson @('network', 'nsg', 'create', '--resource-group', $ResourceGroup,
    '--name', $nsgName, '--location', $Location, '--tags', 'app=releaseproof') | Out-Null
foreach ($rule in @(
    @{ Name = 'operator-ssh'; Priority = '100'; Source = "$operatorIp/32"; Port = '22' },
    @{ Name = 'frontdoor-https'; Priority = '110'; Source = 'AzureFrontDoor.Backend'; Port = '443' },
    @{ Name = 'acme-http'; Priority = '120'; Source = 'Internet'; Port = '80' }
)) {
    Invoke-AzJson @('network', 'nsg', 'rule', 'create', '--resource-group', $ResourceGroup,
        '--nsg-name', $nsgName, '--name', $rule.Name, '--priority', $rule.Priority,
        '--access', 'Allow', '--direction', 'Inbound', '--protocol', 'Tcp',
        '--source-address-prefixes', $rule.Source, '--source-port-ranges', '*',
        '--destination-address-prefixes', '*', '--destination-port-ranges', $rule.Port) | Out-Null
}
$vms = Invoke-AzJson @('vm', 'list', '--resource-group', $ResourceGroup)
if ($vms.Count -gt 0 -and ($vms.Count -ne 1 -or $vms[0].name -ne $vmName -or
    $vms[0].tags.app -ne 'releaseproof')) { throw 'Unexpected VM in project resource group' }
if (-not $vms) {
    $bootstrap = Join-Path $PSScriptRoot '../aws/cloud-init.yaml'
    Invoke-AzJson @('vm', 'create', '--resource-group', $ResourceGroup, '--name', $vmName,
        '--location', $Location, '--zone', '1', '--size', $VmSize,
        '--image', 'Canonical:ubuntu-24_04-lts:server:latest', '--admin-username', 'ubuntu',
        '--authentication-type', 'ssh', '--ssh-key-values', "$key.pub",
        '--custom-data', $bootstrap, '--os-disk-size-gb', '128', '--storage-sku', 'StandardSSD_LRS',
        '--vnet-name', 'releaseproof-vnet', '--subnet', 'releaseproof-subnet',
        '--nsg', $nsgName, '--nsg-rule', 'NONE', '--public-ip-address', 'releaseproof-ip',
        '--public-ip-sku', 'Standard', '--public-ip-address-allocation', 'static',
        '--public-ip-address-dns-name', $dnsName, '--tags', 'app=releaseproof') | Out-Null
}
$publicIp = Invoke-AzJson @('network', 'public-ip', 'show', '--resource-group', $ResourceGroup,
    '--name', 'releaseproof-ip')
$originHost = $publicIp.dnsSettings.fqdn

$frontDoorInfo = Invoke-AzJson @('afd', 'profile', 'create', '--resource-group', $ResourceGroup,
    '--profile-name', $frontDoorProfile, '--sku', 'Standard_AzureFrontDoor',
    '--origin-response-timeout-seconds', '240', '--tags', 'app=releaseproof')
$endpoint = Invoke-AzJson @('afd', 'endpoint', 'create', '--resource-group', $ResourceGroup,
    '--profile-name', $frontDoorProfile, '--endpoint-name', $endpointName,
    '--enabled-state', 'Enabled')
Invoke-AzJson @('afd', 'origin-group', 'create', '--resource-group', $ResourceGroup,
    '--profile-name', $frontDoorProfile, '--origin-group-name', 'releaseproof-origin',
    '--probe-request-type', 'GET', '--probe-protocol', 'Https', '--probe-path', '/api/health',
    '--probe-interval-in-seconds', '60', '--sample-size', '4',
    '--successful-samples-required', '1', '--additional-latency-in-milliseconds', '50') | Out-Null
Invoke-AzJson @('afd', 'origin', 'create', '--resource-group', $ResourceGroup,
    '--profile-name', $frontDoorProfile, '--origin-group-name', 'releaseproof-origin',
    '--origin-name', 'releaseproof-vm', '--host-name', $originHost,
    '--origin-host-header', $originHost, '--http-port', '80', '--https-port', '443',
    '--priority', '1', '--weight', '1000', '--enabled-state', 'Enabled',
    '--enforce-certificate-name-check', 'true') | Out-Null
Invoke-AzJson @('afd', 'route', 'create', '--resource-group', $ResourceGroup,
    '--profile-name', $frontDoorProfile, '--endpoint-name', $endpointName,
    '--route-name', 'releaseproof-public', '--origin-group', 'releaseproof-origin',
    '--supported-protocols', 'Http', 'Https', '--patterns-to-match', '/*',
    '--forwarding-protocol', 'HttpsOnly', '--https-redirect', 'Enabled',
    '--link-to-default-domain', 'Enabled', '--enable-caching', 'false') | Out-Null

$state = [ordered]@{
    subscription_id = $SubscriptionId; resource_group = $ResourceGroup; location = $Location
    vm_name = $vmName; vm_size = $VmSize; public_ip = $publicIp.ipAddress; origin_host = $originHost
    nsg_name = $nsgName; frontdoor_profile = $frontDoorProfile; endpoint_name = $endpointName
    frontdoor_id = $frontDoorInfo.frontDoorId; viewer_url = "https://$($endpoint.hostName)"; key_file = $key
}
$stateFile = Join-Path $StateDirectory 'releaseproof.json'
$state | ConvertTo-Json | Set-Content -Encoding utf8 $stateFile
Write-Output "State: $stateFile"
Write-Output "Viewer URL (verify after application deploy): $($state.viewer_url)"
