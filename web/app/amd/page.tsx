import type { Metadata } from "next";
import { AmdClient } from "@/components/amd/amd-client";

export const metadata: Metadata = { title: "AMD AI evidence" };

export default function AmdPage() {
  return <AmdClient />;
}
