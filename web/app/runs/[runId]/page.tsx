import type { Metadata } from "next";
import { RunPageClient } from "@/components/run/run-page-client";

type Params = { params: Promise<{ runId: string }> };

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { runId } = await params;
  return { title: `Run ${decodeURIComponent(runId)}` };
}

export default async function RunPage({ params }: Params) {
  const { runId } = await params;
  const id = decodeURIComponent(runId);
  return <RunPageClient key={id} runId={id} />;
}
