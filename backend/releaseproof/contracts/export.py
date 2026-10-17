"""Export JSON Schemas of the platform contracts to ``<repo>/schemas``."""

from __future__ import annotations

import json
from pathlib import Path

from releaseproof.contracts import ai, profile, runner

OUT = Path(__file__).resolve().parents[3] / "schemas"

MODELS = {
    "runner_request": runner.RunnerRequest,
    "runner_event": runner.RunnerEventEnvelope,
    "observation": runner.Observation,
    "test_plan_proposal": ai.TestPlanProposal,
    "narrative_report": ai.NarrativeReport,
    "alternatives_proposal": ai.AlternativesProposal,
    "profile": profile.Profile,
    "test_catalog": profile.TestCatalog,
}


def main() -> None:
    OUT.mkdir(exist_ok=True)
    for name, model in MODELS.items():
        schema = model.model_json_schema()
        (OUT / f"{name}.schema.json").write_text(
            json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    print(f"wrote {len(MODELS)} schemas to {OUT}")


if __name__ == "__main__":
    main()
