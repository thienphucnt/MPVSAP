import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "MPVSAP Pipeline Telemetry Dashboard",
  description: "Enterprise telemetry dashboard for MPVSAP YouTube Shorts Automation Pipeline",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className="bg-[#0b0f19] text-gray-100 min-h-screen antialiased">
        {children}
      </body>
    </html>
  );
}
