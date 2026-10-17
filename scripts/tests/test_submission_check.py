import json
from pathlib import Path

import submission_check


def test_real_form_copy_fits_standard_limits():
    root = Path(__file__).resolve().parents[2]
    fields = json.loads((root / "pitch/submission_fields.json").read_text())
    for key, low, high in (
        ("title", 5, 50),
        ("short_description", 50, 255),
        ("long_description", 600, 2000),
    ):
        assert low <= len(fields[key]) <= high
    assert submission_check.validate(fields)  # external fields are deliberately not fabricated


def test_fields_require_real_links_and_operator_confirmations():
    fields = {
        "title": "ReleaseProof",
        "short_description": "S" * 100,
        "long_description": "L" * 700,
        "track": "Intelligent Industry",
        "demo_url": "https://demo.example.com",
        "github_url": "https://github.com/example/project",
        "video_url": "https://video.example.com/demo",
        "team_members": ["Author"],
        "rights_and_prior_work_confirmed": True,
        "registrations_confirmed": True,
        "judge_access_verified": True,
        "video_and_pdf_verified": True,
    }
    assert not submission_check.validate(fields)
    fields["demo_url"] = "[[DEMO_URL]]"
    assert submission_check.validate(fields)
