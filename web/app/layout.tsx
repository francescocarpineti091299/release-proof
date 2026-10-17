import type { Metadata, Viewport } from "next";
import { SiteFooter, SiteHeader } from "@/components/layout/site-chrome";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "ReleaseProof: firmware migration assurance", template: "%s · ReleaseProof" },
  description:
    "A firmware can boot and still be impossible to upgrade safely. ReleaseProof checks the migration path, not just the new image.",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1, themeColor: "#020617" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="flex min-h-screen flex-col">
        <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-white focus:px-3 focus:py-2">
          Skip to content
        </a>
        <SiteHeader />
        <main id="main" className="flex-1">
          {children}
        </main>
        <SiteFooter />
      </body>
    </html>
  );
}
