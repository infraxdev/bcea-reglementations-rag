"use client";

import type { ReactNode } from "react";
import type { SearchHit } from "@/lib/types";
import Citation from "./Citation";

// Matches the [n] markers the system prompt requires (see app/retrieval/prompt_assembly.py)
// so they can be swapped for interactive Citation chips instead of showing as raw text.
const CITATION_RE = /\[(\d+)\]/g;

/** The distinct [n] numbers actually cited in `content`, ascending. Used to show only the
 * sources the answer actually references instead of every retrieved candidate. */
export function getCitedIndices(content: string): number[] {
  const indices = new Set<number>();
  for (const match of content.matchAll(new RegExp(CITATION_RE))) {
    indices.add(Number(match[1]));
  }
  return [...indices].sort((a, b) => a - b);
}

export default function MessageText({
  content,
  sources,
  onCitationSelect,
}: {
  content: string;
  sources: SearchHit[];
  onCitationSelect: (chunkId: string) => void;
}) {
  const parts: ReactNode[] = [];
  let lastIndex = 0;

  // A fresh regex per render (rather than resetting a shared module-level one) keeps
  // this safe under concurrent rendering.
  for (const match of content.matchAll(new RegExp(CITATION_RE))) {
    if (match.index > lastIndex) {
      parts.push(content.slice(lastIndex, match.index));
    }
    const n = Number(match[1]);
    // Sources are sent to the model as a 1-indexed [n] list in the same order as
    // `sources` (see prompt_assembly.assemble_user_message), so n - 1 is the lookup.
    parts.push(
      <Citation key={`${match.index}-${n}`} index={n} hit={sources[n - 1]} onSelect={onCitationSelect} />
    );
    lastIndex = match.index + match[0].length;
  }
  if (lastIndex < content.length) {
    parts.push(content.slice(lastIndex));
  }

  return <p className="whitespace-pre-wrap">{parts}</p>;
}
