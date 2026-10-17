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
            ReleaseProof checks the <strong className="text-white">migration path</strong>, not just the new image.
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
        <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
          <RecentRuns />
          <ReferenceCard />
        </div>
      </div>
    </>
  );
}
