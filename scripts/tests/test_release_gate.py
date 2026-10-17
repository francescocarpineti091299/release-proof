from __future__ import annotations

import json

import pytest
import release_gate


@pytest.mark.parametrize(
    "base",
    [
        "http://public.example",
        "https://user:secret@example.org",
        "https://example.org/?token=x",
        "file:///secret",
        "https://example.org/other",
        "https://example.org/#fragment",
    ],
)
def test_download_refuses_insecure_or_credential_bearing_urls(base, tmp_path):
    with pytest.raises(ValueError):
        release_gate.download_pack(base, "RP-1", tmp_path / "pack.zip")


def test_offline_invalid_pack_errors_and_retains_report(tmp_path):
    pack = tmp_path / "invalid.zip"
    pack.write_bytes(b"not a ZIP")
    out = tmp_path / "output"
    args = [
        "--pack",
        str(pack),
        "--configuration",
        "profile",
        "--change",
        "change",
        "--plan",
        "plan",
        "--out",
        str(out),
    ]
    assert release_gate.main(args) == 2
    assert json.loads((out / "gate.json").read_text())["decision"] == "ERROR"
    assert pack.read_bytes() == b"not a ZIP"
    with pytest.raises(SystemExit):
        release_gate.main(args)


@pytest.mark.parametrize("decision,code", [("PASS", 0), ("BLOCK", 1)])
def test_cli_distinguishes_policy_block_from_verification_error(
    tmp_path, monkeypatch, decision, code
):
    monkeypatch.setattr(release_gate, "verify_pack", lambda _: {})
    monkeypatch.setattr(release_gate, "release_decision", lambda *a, **kw: {"decision": decision})
    assert (
        release_gate.main(
            [
                "--pack",
                str(tmp_path / "pack.zip"),
                "--configuration",
                "profile",
                "--change",
                "change",
                "--plan",
                "plan",
                "--out",
                str(tmp_path / "output"),
            ]
        )
        == code
    )


def test_redirects_are_not_followed():
    assert (
        release_gate.NoRedirect().redirect_request(None, None, 302, "", {}, "https://other") is None
    )
