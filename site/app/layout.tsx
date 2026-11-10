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
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Fredoka:wght@500;600;700&family=Inter:wght@400;500;600;700&display=swap"
        />
        <link rel="icon" href="art/mascot.png" />
      </head>
      <body className="font-sans antialiased">{children}</body>
    </html>
  );
}
