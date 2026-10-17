import type { Metadata } from "next";
import { RunPageClient } from "@/components/run/run-page-client";

type Params = { params: Promise<{ runId: string }> };

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { runId } = await params;
  return { title: `Run ${runId}` };
}

export default async function RunPage({ params }: Params) {
  const { runId } = await params;
  // App Router already decoded the segment. Decoding twice corrupts literal %
  // identifiers and can throw URIError for an otherwise valid URL.
  return <RunPageClient key={runId} runId={runId} />;
}
