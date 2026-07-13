import { BookingPage } from "@/components/booking-page";

/**
 * Public booking page route — /booking/{slug}
 *
 * Renders the Calendly-style booking page for an event type. This page is
 * public (no auth required) — anyone with the URL can book a time slot.
 */
export default function BookingPageRoute({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  return <BookingPageSlug slug={params} />;
}

import { use } from "react";

function BookingPageSlug({ slug }: { slug: Promise<{ slug: string }> }) {
  const { slug: slugValue } = use(slug);
  return <BookingPage slug={slugValue} />;
}
