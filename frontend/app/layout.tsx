import type { Metadata } from "next";
import { Caveat, IBM_Plex_Mono, Schibsted_Grotesk } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";

const ui = Schibsted_Grotesk({ subsets: ["latin"], variable: "--font-ui" });
const num = IBM_Plex_Mono({ subsets: ["latin"], weight: ["400", "500"], variable: "--font-num" });
const written = Caveat({ subsets: ["latin"], weight: ["500", "700"], variable: "--font-written" });

export const metadata: Metadata = {
  title: "Keel",
  description: "Paper-to-production back office for small food producers",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className={`${ui.variable} ${num.variable} ${written.variable} antialiased`}>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
