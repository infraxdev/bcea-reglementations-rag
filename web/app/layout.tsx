import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "BCEAO RAG Tester",
  description: "Test interface for the BCEAO regulation RAG pipeline.",
};

const themeInitScript = `
(function () {
  try {
    var stored = localStorage.getItem("theme");
    var dark = stored ? stored === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches;
    document.documentElement.classList.toggle("dark", dark);
  } catch (e) {}
})();
`;

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-dvh antialiased`}
      suppressHydrationWarning
    >
      <head>
        {/* Runs before paint so the stored/system theme applies with no flash. */}
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>
      {/* suppressHydrationWarning: browser extensions (e.g. Grammarly) inject
          data-gr-* attributes into <body> before React hydrates */}
      <body className="flex h-dvh flex-col overflow-hidden font-sans" suppressHydrationWarning>
        {children}
      </body>
    </html>
  );
}
