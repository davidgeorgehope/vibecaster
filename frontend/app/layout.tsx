import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "@/contexts/AuthContext";
import { MarkdownAlternate } from "@/components/MarkdownAlternate";

export const metadata: Metadata = {
  title: {
    default: 'Vibecaster - AI Social Media Automation | Auto-Post to X, LinkedIn, YouTube',
    template: '%s | Vibecaster'
  },
  description: 'Automate your social media with AI. Vibecaster generates and posts content to X (Twitter), LinkedIn, and YouTube using Google Gemini. Free during beta.',
  keywords: ['social media automation', 'AI content generation', 'Twitter automation', 'LinkedIn automation', 'YouTube automation', 'Google Gemini'],
  authors: [{ name: 'Vibecaster' }],
  metadataBase: new URL('https://vibecaster.app'),
  openGraph: {
    title: 'Vibecaster - AI-Powered Social Media Automation',
    description: 'Generate and post content to X, LinkedIn, and YouTube automatically with AI.',
    url: 'https://vibecaster.app',
    siteName: 'Vibecaster',
    type: 'website',
    images: [{ url: '/og-image.png', width: 1200, height: 630, alt: 'Vibecaster - AI Social Media Automation' }],
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Vibecaster - AI Social Media Automation',
    description: 'Automate your social presence with AI-generated content.',
    images: ['/og-image.png'],
  },
  robots: {
    index: true,
    follow: true,
  },
  alternates: {
    canonical: 'https://vibecaster.app',
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased">
        <AuthProvider>
          <MarkdownAlternate />
          {children}
        </AuthProvider>
      </body>
    </html>
  );
}
