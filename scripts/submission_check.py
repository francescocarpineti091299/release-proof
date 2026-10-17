"""Fail-closed check of final submission fields and release proof. No publishing side effects."""

import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


def validate(fields: dict) -> list[str]:
    problems = []
    for key, low, high in (
        ("title", 5, 50),
        ("short_description", 50, 255),
        ("long_description", 600, 2000),
    ):
        text = fields.get(key, "")
        if not isinstance(text, str) or not low <= len(text) <= high or "[[" in text:
            problems.append(f"{key}: expected {low}–{high} characters without placeholders")
    if fields.get("track") != "Intelligent Industry":
        problems.append("confirm the selected track")
    for key in ("demo_url", "github_url", "video_url"):
        value = fields.get(key, "")
        parsed = urlsplit(value) if isinstance(value, str) else urlsplit("")
        if parsed.scheme != "https" or not parsed.hostname or "[[" in value:
            problems.append(f"{key}: final HTTPS URL required")
    members = fields.get("team_members")
    if not isinstance(members, list) or not 1 <= len(members) <= 6 or not all(members):
        problems.append("team_members: list 1–6 actual members")
    for key in (
        "rights_and_prior_work_confirmed",
        "registrations_confirmed",
        "judge_access_verified",
        "video_and_pdf_verified",
    ):
        if fields.get(key) is not True:
            problems.append(f"{key}: operator confirmation required")
    return problems


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fields", default="pitch/submission_fields.json")
    parser.add_argument(
        "--acceptance", required=True, help="fresh strict --require-ai acceptance report"
    )
    args = parser.parse_args()
    fields = json.loads((ROOT / args.fields).read_text(encoding="utf-8"))
    problems = validate(fields)
    reports = json.loads((ROOT / args.acceptance).read_text(encoding="utf-8"))
    needed = {
        "canonical result hash recomputed",
        "deployed backend matches current source",
        "runner code identity recorded",
        "deployed runner matches current source",
        "accepted AMD plan was executed",
        "AMD explainer validated for this run",
        "AMD alternatives validated for this run",
    }
    profiles = {"nrf52840-wolfboot-pqc", "nrf52840-mcuboot-pqc"}
    if {r.get("profile") for r in reports} != profiles:
        problems.append("acceptance must cover both configurations")
    for report in reports:
        passed = {g["gate"] for g in report.get("gates", []) if g["ok"]}
        if not report.get("passed") or not needed <= passed:
            problems.append(f"{report.get('profile')}: strict acceptance is incomplete or failed")
    for problem in problems:
        print("[BLOCKED] " + problem)
    if not problems:
        print(
            "Submission fields and engineering gates pass. "
            "Verify the authenticated event form and submit manually."
        )
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
