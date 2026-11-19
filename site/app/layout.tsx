import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Tallyable · Club event close-out",
  description:
    "Snap your club's receipts. Tallyable checks the math, shows who's owed, and builds the funder report.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        {/* Fonts are served from public/fonts, so visitors never load anything from Google */}
        <style>{`@font-face{font-family:Fredoka;src:url(fonts/fredoka-latin-wght-normal.woff2) format("woff2");font-weight:300 700;font-display:swap}@font-face{font-family:Inter;src:url(fonts/inter-latin-wght-normal.woff2) format("woff2");font-weight:100 900;font-display:swap}`}</style>
        <link rel="icon" href="art/mascot.png" />
      </head>
      <body className="font-sans antialiased">{children}</body>
    </html>
  );
}
