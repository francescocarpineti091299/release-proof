"use client";

import { useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, ArrowRight, Check, Clock, Cpu, Loader2, Play, ShieldAlert, Sparkles } from "lucide-react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { ChangeView, ConfigurationView, TemplateView } from "@/lib/types";
import { formatSeconds, shortCommit } from "@/lib/format";
import { cn, randomKey } from "@/lib/utils";
import { Badge, Chip } from "@/components/ui/chip";
import { Button } from "@/components/ui/button";
import { Card, Empty, KeyValue } from "@/components/ui/card";
import { Hint } from "@/components/ui/hint";

type Step = 1 | 2 | 3;

const STATUS_TONE: Record<string, "green" | "amber" | "neutral"> = { SUPPORTED: "green", EXPERIMENTAL: "amber", UNAVAILABLE: "neutral" };
const STATUS_HELP: Record<string, string> = {
  SUPPORTED: "Passed the end-to-end acceptance gate: build, sign, emulate and evaluate.",
  EXPERIMENTAL: "Runs end to end in development, but has not passed every acceptance gate yet.",
  UNAVAILABLE: "Not selectable: the runner for this configuration is not available.",
};

export function AssessmentWizard() {
  const router = useRouter();
  const configs = useApi("configurations", () => api.listConfigurations());
  const [step, setStep] = useState<Step>(1);
  const [profileId, setProfileId] = useState<string | null>(null);
  const [changeId, setChangeId] = useState<string | null>(null);
  const [idemKey, setIdemKey] = useState<string>("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const top = useRef<HTMLDivElement>(null);
  const reveal = () => requestAnimationFrame(() => top.current?.scrollIntoView({ block: "start", behavior: "smooth" }));

  const profiles = useMemo(() => configs.data ?? [], [configs.data]);
  const profile = profiles.find((p) => p.id === profileId) ?? null;
  const change = profile?.changes.find((c) => c.change_id === changeId) ?? null;

  const chooseProfile = (p: ConfigurationView) => {
    setProfileId(p.id);
    const only = p.changes.length === 1 ? p.changes[0].change_id : null;
    setChangeId(only);
    setIdemKey(randomKey());
    setError(null);
    setStep(2);
    reveal();
  };

  const chooseChange = (c: ChangeView) => {
    setChangeId(c.change_id);
    setIdemKey(randomKey());
    setError(null);
    setStep(3);
    reveal();
  };

  const run = async () => {
    if (!profile || !change || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const created = await api.createRun({
        configuration_id: profile.id,
        change_id: change.change_id,
        plan_id: change.default_plan_id,
        idempotency_key: idemKey || randomKey(),
      });
      router.push(`/runs/${encodeURIComponent(created.run_id)}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setSubmitting(false);
    }
  };

  return (
    <div ref={top} className="scroll-mt-24">
    <Card className="overflow-hidden">
      <ol className="grid grid-cols-3 border-b border-border bg-slate-50 text-sm" aria-label="Assessment steps">
        {(
          [
            [1, "Device & bootloader"],
            [2, "Change"],
            [3, "Review checks"],
          ] as const
        ).map(([n, label]) => {
          const reachable = n === 1 || (n === 2 && profile) || (n === 3 && change);
          const done = step > n;
          return (
            <li key={n} className="border-r border-border last:border-r-0">
              <button
                type="button"
                disabled={!reachable}
                onClick={() => setStep(n)}
                aria-current={step === n ? "step" : undefined}
                className={cn(
                  "flex w-full items-center gap-2 px-3 py-3 text-left font-semibold sm:px-5",
                  step === n ? "bg-white text-slate-950" : "text-slate-500",
                  reachable && step !== n && "hover:bg-white hover:text-slate-900",
                )}
              >
                <span
                  className={cn(
                    "flex h-7 w-7 shrink-0 items-center justify-center rounded-full border-2 text-sm",
                    step === n ? "border-slate-950 bg-slate-950 text-white" : done ? "border-emerald-600 bg-emerald-600 text-white" : "border-slate-300",
                  )}
                >
                  {done ? <Check className="h-4 w-4" aria-hidden /> : n}
                </span>
                <span className="hidden sm:inline">{label}</span>
              </button>
            </li>
          );
        })}
      </ol>

      <div className="p-4 sm:p-6">
        {step === 1 ? (
          <StepConfigurations loading={configs.loading} error={configs.error} profiles={profiles} selected={profileId} onSelect={chooseProfile} onRetry={configs.reload} />
        ) : null}
        {step === 2 && profile ? (
          <StepChange profile={profile} selected={changeId} onSelect={chooseChange} onBack={() => setStep(1)} />
        ) : null}
        {step === 3 && profile && change ? (
          <StepReview
            profile={profile}
            change={change}
            submitting={submitting}
            error={error}
            onBack={() => setStep(2)}
            onRun={run}
          />
        ) : null}
      </div>
    </Card>
    </div>
  );
}

function StepConfigurations({
  loading,
  error,
  profiles,
  selected,
  onSelect,
  onRetry,
}: {
  loading: boolean;
  error?: Error;
  profiles: ConfigurationView[];
  selected: string | null;
  onSelect: (p: ConfigurationView) => void;
  onRetry: () => void;
}) {
  return (
    <div>
      <h3 className="text-lg font-bold">Which device and bootloader are you migrating?</h3>
      <p className="mt-1 text-sm text-slate-600">Only verified configurations are listed. Versions are pinned, so you do not need to provide scripts, flags or flash addresses.</p>
      <div className="mt-4 grid gap-4 md:grid-cols-2">
        {loading ? (
          [0, 1].map((i) => <div key={i} className="h-44 animate-pulse rounded-lg border border-border bg-slate-100" />)
        ) : error ? (
          <div className="md:col-span-2">
            <Empty>
              Could not load configurations: {error.message}.{" "}
              <button type="button" className="font-semibold text-link underline" onClick={onRetry}>
                Retry
              </button>
            </Empty>
          </div>
        ) : profiles.length === 0 ? (
          <div className="md:col-span-2">
            <Empty>No configurations are available right now.</Empty>
          </div>
        ) : (
          profiles.map((p) => {
            const disabled = p.status === "UNAVAILABLE";
            const active = selected === p.id;
            return (
              <button
                key={p.id}
                type="button"
                disabled={disabled}
                onClick={() => onSelect(p)}
                aria-pressed={active}
                className={cn(
                  "group flex flex-col rounded-lg border-2 bg-white p-4 text-left transition-colors",
                  active ? "border-slate-950 ring-2 ring-slate-950/10" : "border-border hover:border-slate-500",
                  disabled && "cursor-not-allowed opacity-50",
                )}
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-slate-500">
                      <Cpu className="h-4 w-4" aria-hidden /> {p.board.name}
                    </div>
                    <div className="mt-1 text-xl font-bold text-slate-950">{p.bootloader.name}</div>
                  </div>
                  <Chip tone={STATUS_TONE[p.status] ?? "neutral"} title={STATUS_HELP[p.status]}>
                    {p.status}
                  </Chip>
                </div>
                <p className="mt-2 text-sm text-slate-600">{p.board.soc}</p>
                <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
                  <dt className="text-slate-500">Bootloader pin</dt>
                  <dd className="font-mono-id truncate text-slate-900">{shortCommit(p.bootloader.commit)} · {p.bootloader.version_label}</dd>
                  {Object.entries(p.toolchain)
                    .slice(0, 2)
                    .map(([k, v]) => (
                      <div key={k} className="contents">
                        <dt className="text-slate-500">{k}</dt>
                        <dd className="font-mono-id truncate text-slate-900">{shortCommit(v)}</dd>
                      </div>
                    ))}
                  <dt className="text-slate-500">Emulator</dt>
                  <dd className="text-slate-900">Renode</dd>
                </dl>
                <span className="mt-4 inline-flex items-center gap-1 text-sm font-semibold text-slate-900 group-disabled:hidden">
                  Select <ArrowRight className="h-4 w-4" aria-hidden />
                </span>
              </button>
            );
          })
        )}
      </div>
    </div>
  );
}

function StepChange({
  profile,
  selected,
  onSelect,
  onBack,
}: {
  profile: ConfigurationView;
  selected: string | null;
  onSelect: (c: ChangeView) => void;
  onBack: () => void;
}) {
  return (
    <div>
      <h3 className="text-lg font-bold">What change do you want to ship?</h3>
      <p className="mt-1 text-sm text-slate-600">
        Changes supported by <strong>{profile.title}</strong>. Each one comes with a default rollout plan; you can explore alternatives after the first result.
      </p>
      <div className="mt-4 space-y-3">
        {profile.changes.map((c) => (
          <div key={c.change_id} className={cn("rounded-lg border-2 bg-white", selected === c.change_id ? "border-slate-950" : "border-border")}>
            <button type="button" onClick={() => onSelect(c)} className="flex w-full flex-col gap-2 p-4 text-left hover:bg-slate-50 sm:flex-row sm:items-center">
              <div className="min-w-0 flex-1">
                <div className="text-base font-bold text-slate-950">{c.title}</div>
                <p className="mt-1 text-sm text-slate-600">{c.summary}</p>
                <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
                  <Badge>{c.from_scheme}</Badge>
                  <ArrowRight className="h-3.5 w-3.5 text-slate-400" aria-hidden />
                  <Badge className="border-emerald-400 text-emerald-800">{c.to_scheme}</Badge>
                  <span className="text-slate-500">Plan: {c.default_plan_title}</span>
                </div>
              </div>
              <span className="inline-flex items-center gap-1 text-sm font-semibold">
                Choose <ArrowRight className="h-4 w-4" aria-hidden />
              </span>
            </button>
            <details className="border-t border-border px-4 py-2 text-sm">
              <summary className="font-semibold text-slate-600 hover:text-slate-900">Advanced details</summary>
              <div className="py-3">
                <KeyValue
                  rows={[
                    ["Change id", c.change_id],
                    ["Default plan", `${c.default_plan_id}`],
                    ["Profile version", profile.version],
                    ["Ruleset", `V${profile.ruleset_version}`],
                    ["Runner image", profile.runner_image],
                    ["Time budget", formatSeconds(profile.timeout_seconds)],
                    ["Platform script", profile.board.platform_script],
                    ["Bootloader repo", profile.bootloader.repo],
                    ["Bootloader commit", profile.bootloader.commit],
                    ["License", profile.bootloader.license],
                    ...Object.entries(profile.toolchain).map(([k, v]) => [k, v] as [string, string]),
                  ]}
                />
                {profile.known_limitations.length ? (
                  <div className="mt-3">
                    <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Known limitations</div>
                    <ul className="mt-1 list-disc pl-5 text-slate-700">
                      {profile.known_limitations.map((l) => (
                        <li key={l}>{l}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </div>
            </details>
          </div>
        ))}
      </div>
      <div className="mt-5">
        <Button variant="ghost" onClick={onBack}>
          <ArrowLeft className="h-4 w-4" aria-hidden /> Back
        </Button>
      </div>
    </div>
  );
}

function CheckRow({ id, template, kind }: { id: string; template: TemplateView | undefined; kind: "required" | "optional" }) {
  return (
    <li className="flex items-start gap-3 py-2.5">
      <span className={cn("mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full", kind === "required" ? "bg-slate-950 text-white" : "border border-dashed border-violet-400 text-violet-700")}>
        {kind === "required" ? <Check className="h-3.5 w-3.5" aria-hidden /> : <Sparkles className="h-3.5 w-3.5" aria-hidden />}
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-semibold text-slate-900">{template?.title ?? id}</span>
          {template?.negative ? (
            <Chip tone="slate" size="xs" title="Negative test: it passes when the bootloader refuses something it must refuse.">
              <ShieldAlert className="h-3 w-3" aria-hidden /> Negative test
            </Chip>
          ) : null}
        </div>
        <div className="mt-0.5 text-xs text-slate-500">
          <span className="font-mono-id">{template?.test_id ?? "?"}</span> · {template?.expected ?? id}
        </div>
      </div>
      <span className="flex shrink-0 items-center gap-1 text-xs text-slate-500">
        <Clock className="h-3.5 w-3.5" aria-hidden /> {template ? `~${formatSeconds(template.est_seconds)}` : "—"}
      </span>
    </li>
  );
}

function StepReview({
  profile,
  change,
  submitting,
  error,
  onBack,
  onRun,
}: {
  profile: ConfigurationView;
  change: ChangeView;
  submitting: boolean;
  error: string | null;
  onBack: () => void;
  onRun: () => void;
}) {
  const required = change.templates.filter((t) => t.required);
  const optional = change.templates.filter((t) => !t.required);
  const minT = required.reduce((acc, t) => acc + t.est_seconds, 0);
  const maxT = change.est_seconds_total || minT + optional.reduce((acc, t) => acc + t.est_seconds, 0);
  return (
    <div>
      <h3 className="text-lg font-bold">Review the planned checks</h3>
      <p className="mt-1 text-sm text-slate-600">
        <strong>{profile.title}</strong> · {change.title}
      </p>

      <div className="mt-4 grid gap-4 lg:grid-cols-[1fr_20rem]">
        <div className="space-y-4">
          <div className="rounded-lg border border-border bg-white px-4 py-2">
            <div className="flex items-center justify-between pt-2">
              <h4 className="text-sm font-bold uppercase tracking-wide text-slate-700">Always run ({required.length})</h4>
              <Hint text="Required by the profile policy. The AI cannot remove them." />
            </div>
            <ul className="divide-y divide-border">
              {required.map((t) => (
                <CheckRow key={t.template_id} id={t.template_id} template={t} kind="required" />
              ))}
            </ul>
          </div>
          {optional.length ? (
            <div className="rounded-lg border border-dashed border-violet-300 bg-violet-50/40 px-4 py-2">
              <div className="flex items-center justify-between pt-2">
                <h4 className="text-sm font-bold uppercase tracking-wide text-violet-900">AI may add ({optional.length})</h4>
                <Hint text="The AMD-hosted planner picks which of these registered checks to run and explains why. It cannot invent tests: unregistered proposals are blocked." />
              </div>
              <ul className="divide-y divide-violet-200">
                {optional.map((t) => (
                  <CheckRow key={t.template_id} id={t.template_id} template={t} kind="optional" />
                ))}
              </ul>
            </div>
          ) : null}
        </div>

        <aside className="flex flex-col gap-4 rounded-lg bg-slate-950 p-5 text-white">
          <div>
            <div className="text-xs font-semibold uppercase tracking-wider text-slate-400">Estimated test time</div>
            <div className="mt-1 text-2xl font-bold">
              {minT === maxT ? formatSeconds(minT) : `${formatSeconds(minT)} – ${formatSeconds(maxT)}`}
            </div>
            <p className="mt-1 text-xs text-slate-400">Depends on the AI plan and on the queue. Progress is streamed live from the runner, with no simulated percentages.</p>
          </div>
          <ul className="space-y-1.5 text-sm text-slate-200">
            <li>• Real builds and signatures with pinned tools</li>
            <li>• Boot and update tests in Renode</li>
            <li>• Verdict from the deterministic V1.2 engine</li>
          </ul>
          {error ? <p className="rounded bg-red-900/60 px-3 py-2 text-sm text-red-100" role="alert">{error}</p> : null}
          <Button size="lg" onClick={onRun} disabled={submitting} className="bg-emerald-500 text-black hover:bg-emerald-400 disabled:bg-emerald-800 disabled:text-emerald-200">
            {submitting ? <Loader2 className="h-5 w-5 animate-spin" aria-hidden /> : <Play className="h-5 w-5" aria-hidden />}
            {submitting ? "Starting…" : "Run assessment"}
          </Button>
          <button type="button" onClick={onBack} className="text-sm font-semibold text-slate-300 hover:text-white" disabled={submitting}>
            ← Change selection
          </button>
        </aside>
      </div>
    </div>
  );
}
