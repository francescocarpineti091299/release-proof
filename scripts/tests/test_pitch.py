"""Prevent stale exports, visible placeholders and form-copy regressions."""

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_submission_copy_fits_standard_form_limits():
    text = (ROOT / "pitch/submission.md").read_text(encoding="utf-8")
    title = re.search(r"## Title\s+\*\*(.*?)\*\*", text).group(1)
    short = text.split("## Short description", 1)[1].split("## Long description", 1)[0]
    short = " ".join(line[2:] for line in short.splitlines() if line.startswith("> "))
    long = text.split("## Long description", 1)[1].split("\n## ", 1)[0].strip()
    assert 5 <= len(title) <= 50
    assert 50 <= len(short) <= 255
    assert 600 <= len(long) <= 2000


def test_exported_deck_matches_sources_and_has_ten_placeholder_free_slides():
    pitch = ROOT / "pitch"
    text = (pitch / "slides.html").read_text(encoding="utf-8")
    assert re.findall(r'<section class="slide [^"]+" id="s(\d+)"', text) == [
        str(i) for i in range(1, 11)
    ]
    assert "[[" not in text
    report = json.loads((pitch / "export-manifest.json").read_text(encoding="utf-8"))
    assert report["pages"] == 10 and report["overflow"] == [] and not report["placeholders"]
    assert report["wrongSize"] == []
    for name, digest in report["sha256"].items():
        assert hashlib.sha256((pitch / name).read_bytes()).hexdigest() == digest, (
            f"{name} changed; run node scripts/export_pitch.mjs"
        )
    assert (pitch / "slides.pdf").read_bytes().startswith(b"%PDF")
