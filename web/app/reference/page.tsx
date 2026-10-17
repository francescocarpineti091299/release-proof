import type { Metadata } from "next";
import { ReferenceClient } from "@/components/reference/reference-client";

export const metadata: Metadata = { title: "Reference run (recorded)" };

export default function ReferencePage() {
  return <ReferenceClient />;
}
