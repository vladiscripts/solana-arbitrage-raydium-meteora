import type { Metadata } from "next";
import NextHead from "next/head";

import localFont from "next/font/local";
import "./globals.css";

const geistSans = localFont({
  src: "./fonts/GeistVF.woff",
  variable: "--font-geist-sans",
  weight: "100 900",
});
const geistMono = localFont({
  src: "./fonts/GeistMonoVF.woff",
  variable: "--font-geist-mono",
  weight: "100 900",
});

export const metadata: Metadata = {
  title: "Solana Arbitrage",
  description: "Next Solana Arbitrage",
  icons: {
    icon: "/favicon.ico",  // Add your favicon here
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {

  return (
    <html lang="en">
      <NextHead>
        <link href="/favicon.ico" rel="icon" />
        <link rel="icon" type="image/png" href="/favicon.png" />
        <link rel="apple-touch-icon" href="/apple-touch-icon.png" />
        <meta name="theme-color" content="#060606" />
      </NextHead>
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased bg-[#060606] dotted-bg`}
      >
        {children}
      </body>
    </html>
  );
}
