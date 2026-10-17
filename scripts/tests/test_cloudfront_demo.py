from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG = json.loads((ROOT / "deploy/aws/cloudfront-demo.json").read_text())
DISTRIBUTION = CONFIG["DistributionConfigWithTags"]["DistributionConfig"]


def test_demo_uses_managed_viewer_tls_and_validated_https_origin():
    assert DISTRIBUTION["ViewerCertificate"] == {"CloudFrontDefaultCertificate": True}
    assert DISTRIBUTION["DefaultCacheBehavior"]["ViewerProtocolPolicy"] == "redirect-to-https"
    origins = DISTRIBUTION["Origins"]
    assert origins["Quantity"] == len(origins["Items"]) == 1
    origin = origins["Items"][0]
    assert origin["CustomOriginConfig"]["OriginProtocolPolicy"] == "https-only"
    assert origin["CustomOriginConfig"]["OriginSslProtocols"]["Items"] == ["TLSv1.2"]
    assert origin["Id"] == DISTRIBUTION["DefaultCacheBehavior"]["TargetOriginId"]


def test_no_route_can_cache_api_results_or_live_events():
    behavior = DISTRIBUTION["DefaultCacheBehavior"]
    assert behavior["CachePolicyId"] == "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"
    assert DISTRIBUTION["CacheBehaviors"]["Quantity"] == 0
    errors = DISTRIBUTION["CustomErrorResponses"]
    assert errors["Quantity"] == len(errors["Items"])
    assert all(error["ErrorCachingMinTTL"] == 0 for error in errors["Items"])


def test_forward_viewer_parameters_but_use_origin_host_for_tls():
    # Managed AllViewerExceptHostHeader forwards Authorization, cookies, query
    # strings, Next.js RSC headers and SSE cursors without replacing origin SNI.
    behavior = DISTRIBUTION["DefaultCacheBehavior"]
    assert behavior["OriginRequestPolicyId"] == "b689b0a8-53d0-40ab-baf2-68738e2966ac"
    assert DISTRIBUTION["Origins"]["Items"][0]["CustomHeaders"]["Quantity"] == 0


def test_live_run_creation_and_streaming_are_supported():
    methods = DISTRIBUTION["DefaultCacheBehavior"]["AllowedMethods"]
    assert methods["Quantity"] == len(methods["Items"]) == 7
    assert set(methods["Items"]) == {"GET", "HEAD", "OPTIONS", "PUT", "PATCH", "POST", "DELETE"}
    assert DISTRIBUTION["Origins"]["Items"][0]["CustomOriginConfig"]["OriginReadTimeout"] == 60


def test_distribution_is_identifiable_and_recreation_is_idempotent():
    assert DISTRIBUTION["CallerReference"].startswith("releaseproof-demo-")
    tags = CONFIG["DistributionConfigWithTags"]["Tags"]["Items"]
    assert {"Key": "app", "Value": "releaseproof"} in tags
    assert DISTRIBUTION["PriceClass"] == "PriceClass_100"
    assert DISTRIBUTION["Enabled"] is True
