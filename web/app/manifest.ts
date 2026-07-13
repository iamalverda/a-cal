import type { MetadataRoute } from "next";

/**
 * PWA manifest — makes A-Cal installable on desktop and mobile.
 *
 * Users can "Add to Home Screen" on iOS/Android or "Install" in Chrome/Edge
 * to run A-Cal as a native-like app. This aligns with the charter's
 * self-hostable, runnable-anywhere vision.
 */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "A-Cal — Agentic Calendar",
    short_name: "A-Cal",
    description:
      "An agentic, self-hostable calendar platform that unifies all your accounts and email providers under one intelligent, fully customizable system.",
    start_url: "/",
    display: "standalone",
    background_color: "#0a0a0a",
    theme_color: "#6366f1",
    orientation: "any",
    categories: ["productivity", "calendar", "utilities"],
    icons: [
      {
        src: "/icon.svg",
        sizes: "any",
        type: "image/svg+xml",
        purpose: "any",
      },
      {
        src: "/icon.svg",
        sizes: "512x512",
        type: "image/svg+xml",
        purpose: "maskable",
      },
    ],
  };
}
