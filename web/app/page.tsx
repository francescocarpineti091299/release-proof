import { Bot, Cpu, Scale } from "lucide-react";
import { AssessmentWizard } from "@/components/home/wizard";
import { RecentRuns, ReferenceCard } from "@/components/home/recent-runs";

export default function HomePage() {
  return (
    <>
      <section className="border-b border-slate-800 bg-slate-950 text-white">
        <div className="mx-auto max-w-7xl px-4 pb-12 pt-10 sm:px-6 sm:pt-14">
          <p className="text-sm font-semibold uppercase tracking-widest text-emerald-400">Firmware migration assurance</p>
          <h1 className="mt-3 max-w-4xl text-3xl font-extrabold leading-tight tracking-tight sm:text-5xl">
            A firmware can boot and still be impossible to upgrade safely.
          </h1>
          <p className="mt-4 max-w-3xl text-lg text-slate-300 sm:text-xl">
            Help industrial IoT firmware teams verify that an update can reach their installed devices—
            <strong className="text-white"> not just boot on a new one</strong>—before rollout.
          </p>
          <ul className="mt-8 grid gap-4 text-sm sm:grid-cols-3">
            <li className="flex gap-3 rounded-lg border border-slate-800 bg-slate-900 p-4">
              <Cpu className="h-6 w-6 shrink-0 text-sky-400" aria-hidden />
              <span>
                <strong className="block text-white">Real builds, real emulation</strong>
                <span className="text-slate-400">Pinned toolchains build and sign the images; Renode boots and updates them.</span>
              </span>
            </li>
            <li className="flex gap-3 rounded-lg border border-slate-800 bg-slate-900 p-4">
              <Bot className="h-6 w-6 shrink-0 text-violet-400" aria-hidden />
              <span>
                <strong className="block text-white">AMD-hosted AI plans and explains</strong>
                <span className="text-slate-400">It picks registered tests, explains blockers and proposes alternative plans.</span>
              </span>
            </li>
            <li className="flex gap-3 rounded-lg border border-slate-800 bg-slate-900 p-4">
              <Scale className="h-6 w-6 shrink-0 text-emerald-400" aria-hidden />
              <span>
                <strong className="block text-white">Deterministic verdict</strong>
                <span className="text-slate-400">A rule engine decides, citing evidence. The AI never issues the verdict.</span>
              </span>
            </li>
          </ul>
        </div>
      </section>

      <div className="mx-auto -mt-6 max-w-7xl space-y-8 px-4 sm:px-6">
        <div>
          <h2 className="sr-only">New assessment</h2>
          <AssessmentWizard />
        </div>
        <section aria-labelledby="industrial-scope" className="rounded-lg border border-border bg-white p-5">
          <h2 id="industrial-scope" className="text-lg font-bold text-slate-950">A preflight check for long-lived industrial sensors</h2>
          <p className="mt-2 text-sm text-slate-700">For firmware leads and product-security teams at device OEMs: find update-path blockers before risking a field intervention or loss of monitoring continuity. The first supported change is ECDSA P-256 → ML-DSA on two nRF52840 bootloader configurations, not arbitrary firmware updates.</p>
          <p className="mt-2 text-sm text-slate-600">nRF52840 is used in documented wireless condition-monitoring products such as <a href="https://www.nordicsemi.com/Nordic-news/2019/09/National-Instruments-employs-nRF52840-to-wirelessly-transmit-asset-health-data" target="_blank" rel="noreferrer" className="font-semibold text-link hover:underline">NI MON-10411</a>. This establishes hardware relevance, not support for NI firmware or a customer relationship.</p>
          <p className="mt-3 border-t border-border pt-3 text-xs font-semibold text-slate-600">Before OTA, not an OTA platform. Emulation, not hardware validation. Engineering evidence, not certification. No fleet-wide safety or measured ROI claim.</p>
        </section>
        <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
          <RecentRuns />
          <ReferenceCard />
        </div>
      </div>
    </>
  );
}
