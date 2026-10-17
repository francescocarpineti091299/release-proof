# ReleaseProof public demo through CloudFront

Dedicated viewer URL: **https://d1yxcnwgdgjzt6.cloudfront.net**

Distribution ID: `EYOV800QNV3V` (AWS account containing the demo EC2 instance).
Created and confirmed **Deployed** on 2026-10-17. Viewer access was verified from
the Windows demo workstation with normal TLS checks in Python, Windows curl and
an isolated Edge browser session. The rendered UI showed both supported profiles
without a certificate interstitial.

Live transport smoke: **PASS**, recorded in
[`../../docs/acceptance/cloudfront-demo-smoke-20261017.json`](../../docs/acceptance/cloudfront-demo-smoke-20261017.json).
Run `RP-20261017T143902Z-3d53b7` completed with pipeline status `SUCCEEDED`, delivered
248 SSE events and a hash-verified manifest through the viewer URL. Pipeline success
does not mean the migration is compatible; the MCUboot migration verdict remains
`INCOMPATIBLE`, as expected for its unsupported ML-DSA verifier.

The EC2 origin is `https://52-30-20-1.sslip.io`. Some corporate networks block
dynamic-DNS hostnames or intercept their TLS connections with an untrusted
certificate. The submission URL should therefore use the dedicated CloudFront
distribution, not the dynamic-DNS origin hostname.

`cloudfront-demo.json` defines a distribution for this demo only:

- AWS-managed HTTPS certificate on the assigned `*.cloudfront.net` viewer hostname.
- HTTPS-only origin connections with certificate validation; no TLS verification bypass.
- HTTP viewer requests redirect to HTTPS.
- Managed `CachingDisabled` policy on all routes, including UI, API, results and live events.
- Managed `AllViewerExceptHostHeader` policy forwards cookies, query parameters and
  viewer headers (including Authorization, Next.js RSC and Last-Event-ID). CloudFront
  uses the origin hostname for Host/SNI so the origin certificate matches.
- All seven HTTP methods are forwarded; the application still controls valid routes.
- A 60-second origin idle-read timeout accommodates the live event stream.
- No application, database, runner, origin certificate or existing distribution is replaced.

## Origin network and latest infrastructure check

See [`../../docs/INFRA_AUDIT_2026-10-17.md`](../../docs/INFRA_AUDIT_2026-10-17.md).
Origin TCP/443 now accepts only AWS's CloudFront origin-facing prefix list; operator SSH
is unchanged, public HTTP/80 remains for ACME HTTP-01, and unused origin IPv6/QUIC ingress
was removed. This does not disable viewer HTTP/3. Direct HTTPS origin checks from the
operator's workstation are intentionally blocked: use the viewer URL or loopback over SSH.
The prefix list allows CloudFront generally, not exclusively this distribution.

Provisioning supports `--cloudfront-origin` and preserves an existing CloudFront-only rule.
Use `deploy.sh --viewer-url https://d1yxcnwgdgjzt6.cloudfront.net` for future deployment checks.
The source `SITE_ADDRESS` must remain the origin hostname, not the viewer hostname.

Post-cleanup read-only UI/API/result/manifest checks passed. Private research copies and
893.9 MB of superseded build cache were removed; persistent data/current images were retained.
The older AWS runtime is still anonymous, lacks new API budget limits and uses root runners
with the full data volume. Do not infer repository hardening from CloudFront's presence.

## Create and verify

From the repository root, use an explicitly selected AWS profile with CloudFront
permissions in the same account as the demo instance:

```powershell
aws --profile <demo-profile> cloudfront create-distribution-with-tags `
  --cli-input-json file://deploy/aws/cloudfront-demo.json

aws --profile <demo-profile> cloudfront wait distribution-deployed --id <distribution-id>

curl.exe --fail --show-error https://<assigned-hostname>.cloudfront.net/api/health
```

Before creating anything, list existing distributions and reuse this demo's
distribution if it already exists. The caller reference is intentionally stable
to prevent accidental duplicate creation. For a different origin, update this
demo's existing distribution with its latest ETag instead of creating another.

Check the UI, configuration list, a run creation, SSE events and downloaded evidence
through the **viewer URL**, with normal certificate verification enabled. A cloud-side
origin check alone does not establish that a browser can reach the viewer URL.

```powershell
python scripts/cloudfront_smoke.py --base https://d1yxcnwgdgjzt6.cloudfront.net --live `
  --output docs/acceptance/cloudfront-demo-smoke.json
```

`--live` creates one real MCUboot assessment and also verifies an idempotent POST
retry, live SSE, the resulting verdict and the manifest download/hash. Without
`--live`, it performs read-only UI/API checks and checks an existing run if present.
This is an access/transport smoke test, not the full profile acceptance gate.

CloudFront does not add or remove application authentication. Keep the public
gateway and API capacity limits appropriate for the demo; do not upload sensitive
firmware or credentials. Corporate policies can still block a viewer hostname;
request approval from the network administrator in that case rather than disabling
browser or network security.

Normal CloudFront request/transfer charges apply. The distribution uses
`PriceClass_100` (North America and Europe); caching is intentionally disabled for
correctness. Retain it for judging, then disable/delete this demo distribution
when the public demo is no longer needed. Fetch the current ETag when disabling,
wait for deployment, fetch the new ETag before deletion and verify the resource tag/ID.
`destroy.sh` does not remove CloudFront. Do not modify other distributions or AWS-managed policies.
