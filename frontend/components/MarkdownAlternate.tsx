"use client";

import { usePathname } from "next/navigation";
import { useEffect } from "react";

export function MarkdownAlternate() {
  const pathname = usePathname();

  useEffect(() => {
    // Only add for the landing page which has a markdown version
    if (pathname !== "/") return;

    const mdPath = "/page.md";

    // Check if link already exists
    const existing = document.querySelector('link[rel="alternate"][type="text/markdown"]');
    if (existing) {
      existing.setAttribute("href", mdPath);
      return;
    }

    // Create and append the link tag
    const link = document.createElement("link");
    link.rel = "alternate";
    link.type = "text/markdown";
    link.href = mdPath;
    link.title = "Markdown version";
    document.head.appendChild(link);

    return () => {
      link.remove();
    };
  }, [pathname]);

  return null;
}
