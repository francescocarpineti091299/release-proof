"""Dossier is deterministic and marks official=false."""

from __future__ import annotations

from releaseproof.core.assurance.service import evaluate
from releaseproof.core.dossier.service import render_dossier_markdown
from releaseproof.core.projection.wp0 import build_wp0_baseline_assessment


def test_dossier_contains_verdict_and_official_false() -> None:
    assessment = build_wp0_baseline_assessment()
    result = evaluate(assessment).model_dump(mode="json")
    md = render_dossier_markdown(assessment, result)
    assert "official=false" in md
    assert "INCOMPATIBLE" in md
    assert result["assessment_id"] in md
    assert "Contrary evidence" in md
    second = render_dossier_markdown(assessment, result)
    assert md == second
