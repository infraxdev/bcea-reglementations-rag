"use client";

import type { SearchHit } from "@/lib/types";

export default function Citation({
  index,
  hit,
  onSelect,
}: {
  index: number;
  hit: SearchHit | undefined;
  onSelect: (chunkId: string) => void;
}) {
  // The model cited a number with no matching entry in `sources` (e.g. a hallucinated
  // or out-of-range [n]) — render it inert rather than a button that opens nothing.
  if (!hit) {
    return <sup className="mx-0.5 text-muted-foreground">[{index}]</sup>;
  }

  const label = hit.title ?? hit.source_url;
  const tooltip = label + (hit.page_number != null ? `, p.${hit.page_number}` : "");

  return (
    <button
      type="button"
      onClick={() => onSelect(hit.chunk_id)}
      title={tooltip}
      aria-label={`Source ${index}: ${tooltip}`}
      className="mx-0.5 inline-flex h-[1.1em] min-w-[1.1em] -translate-y-px items-center justify-center rounded-full bg-accent/15 px-1 align-middle text-[10px] font-medium leading-none text-accent transition-colors hover:bg-accent hover:text-accent-foreground"
    >
      {index}
    </button>
  );
}
