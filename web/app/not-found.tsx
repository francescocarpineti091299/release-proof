import Link from "next/link";
import { buttonClass } from "@/components/ui/button";

export default function NotFound() {
  return (
    <div className="mx-auto max-w-2xl px-6 py-20 text-center">
      <h1 className="text-2xl font-bold">Page not found</h1>
      <p className="mt-2 text-slate-600">The page or run you are looking for does not exist.</p>
      <Link href="/" className={buttonClass("primary", "md", "mt-6")}>
        Start a new assessment
      </Link>
    </div>
  );
}
