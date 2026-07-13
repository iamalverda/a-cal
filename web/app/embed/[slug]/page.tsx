import { BookingPage } from "@/components/booking-page";

/**
 * Embeddable booking page route — /embed/{slug}
 *
 * Same booking experience as /booking/{slug} but designed for iframe
 * embedding. Renders without the full app chrome so it fits cleanly
 * inside an iframe on external sites.
 */
export default function EmbedPageRoute({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  return <EmbedPageSlug slug={params} />;
}

import { use } from "react";

function EmbedPageSlug({ slug }: { slug: Promise<{ slug: string }> }) {
  const { slug: slugValue } = use(slug);
  return <BookingPage slug={slugValue} isEmbed />;
}
