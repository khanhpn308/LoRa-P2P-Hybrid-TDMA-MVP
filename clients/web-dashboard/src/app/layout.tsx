import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({
  subsets: ["latin", "vietnamese"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: "IIoT LoRa Network Dashboard",
  description: "Industrial LoRa Event-Driven Fault Monitoring Web Dashboard",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="vi" className={inter.variable}>
      <body className="min-h-screen antialiased bg-canvas text-text-primary">
        {children}
      </body>
    </html>
  );
}

