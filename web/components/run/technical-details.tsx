"use client";

import { Download } from "lucide-react";
import { formatTimestamp } from "@/lib/format";
import type { ArtifactView, ResultView, RunView } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Collapsible, KeyValue } from "@/components/ui/card";
import { Markdown } from "@/components/ui/markdown";
import { ArtifactsTable } from "./evidence";

function download(name: string, data: unknown) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function TechnicalDetails({ run, result, artifacts }: { run: RunView; result: ResultView | null; artifacts: ArtifactView[] }) {
  const assessment = result?.assessment;
  const ruleset = assessment && typeof assessment.ruleset_ref === "object" && assessment.ruleset_ref ? (assessment.ruleset_ref as Record<string, unknown>) : null;
  return (
    <div className="space-y-3">
      <Collapsible summary="Identity & reproducibility" defaultOpen>
        <div className="grid gap-6 lg:grid-cols-2">
          <KeyValue
            rows={[
              ["Run id", run.run_id],
              ["Mode", run.mode],
              ["Configuration", `${run.configuration_id}@${run.configuration_version}`],
              ["Change", run.change_id],
              ["Plan", run.plan_id],
              ["Parent run", run.parent_run_id ?? "—"],
              ["Created", formatTimestamp(run.created_at)],
              ["Started", formatTimestamp(run.started_at)],
              ["Finished", formatTimestamp(run.finished_at)],
            ]}
          />
          <KeyValue
            rows={[
              ["Canonical hash", run.verdict?.canonical_hash ?? result?.result.canonical_hash ?? "—"],
              ["Manifest sha256", result?.manifest_sha256 ?? "—"],
              ["Contract", `V${assessment?.contract_version ?? "1.2"}`],
              ["Ruleset", ruleset ? `${String(ruleset.id ?? "")} ${String(ruleset.version ?? "")}` : "RULESET-V1.2"],
              ["Assessment id", result?.result.assessment_id ?? "—"],
              ["Lifecycle", run.verdict?.lifecycle ?? result?.result.lifecycle ?? "—"],
              ["official", "false"],
            ]}
          />
        </div>
        {result ? (
          <div className="mt-4 flex flex-wrap gap-2">
            <Button variant="secondary" size="sm" onClick={() => download(`${run.run_id}-result.json`, result.result)}>
              <Download className="h-4 w-4" aria-hidden /> Result JSON
            </Button>
            <Button variant="secondary" size="sm" onClick={() => download(`${run.run_id}-assessment.json`, result.assessment)}>
              <Download className="h-4 w-4" aria-hidden /> Assessment JSON
            </Button>
          </div>
        ) : null}
      </Collapsible>
      <Collapsible summary={`Source pins & tool versions (${Object.keys(run.source_pins).length + Object.keys(run.tool_versions).length})`}>
        <div className="grid gap-6 lg:grid-cols-2">
          <div>
            <h4 className="mb-2 text-xs font-bold uppercase tracking-wide text-slate-500">Source pins</h4>
            <KeyValue rows={Object.entries(run.source_pins)} />
          </div>
          <div>
            <h4 className="mb-2 text-xs font-bold uppercase tracking-wide text-slate-500">Tool versions</h4>
            <KeyValue rows={Object.entries(run.tool_versions)} />
          </div>
        </div>
      </Collapsible>
      <Collapsible summary={`Artifacts (${artifacts.length})`}>
        <ArtifactsTable artifacts={artifacts} />
      </Collapsible>
      {result?.dossier_markdown ? (
        <Collapsible summary="Assessment dossier (markdown)">
          <Markdown content={result.dossier_markdown} />
        </Collapsible>
      ) : null}
    </div>
  );
}
