"use client";

import { forwardRef, useImperativeHandle, useRef, useState } from "react";
import { ExternalLink } from "lucide-react";
import type { SearchHit } from "@/lib/types";

export interface SourceListHandle {
  /** Opens and scrolls to the card for `chunkId`. Used by inline [n] citations (see
   * MessageText/Citation) so clicking one jumps straight to its source instead of
   * leaving the reader to scan the list themselves. */
  focus: (chunkId: string) => void;
}

/** A source paired with the [n] number it's cited as inline, so the badge here matches
 * the citation chip in the answer text even though this list only shows cited sources. */
export interface NumberedSource {
  number: number;
  hit: SearchHit;
}

const SourceList = forwardRef<SourceListHandle, { sources: NumberedSource[] }>(function SourceList(
  { sources },
  ref
) {
  const [openId, setOpenId] = useState<string | null>(null);
  const itemRefs = useRef<Record<string, HTMLLIElement | null>>({});

  useImperativeHandle(ref, () => ({
    focus(chunkId) {
      setOpenId(chunkId);
      itemRefs.current[chunkId]?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    },
  }));

  if (sources.length === 0) return null;

  return (
    <div className="mt-3 border-t border-border pt-3">
      <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        Sources ({sources.length})
      </p>
      <ul className="space-y-1.5">
        {sources.map(({ number, hit }) => {
          const open = openId === hit.chunk_id;
          return (
            <li
              key={hit.chunk_id}
              ref={(el) => {
                itemRefs.current[hit.chunk_id] = el;
              }}
            >
              <button
                type="button"
                onClick={() => setOpenId(open ? null : hit.chunk_id)}
                className="flex w-full items-center gap-2 rounded-full border border-border px-3 py-1.5 text-left text-sm transition-colors hover:border-border-strong hover:bg-surface-2"
              >
                <span className="flex size-4 shrink-0 items-center justify-center rounded-full bg-accent/15 text-[10px] font-medium text-accent">
                  {number}
                </span>
                <span className="min-w-0 flex-1 truncate text-foreground">
                  {hit.title ?? hit.source_url}
                  {hit.page_number != null && (
                    <span className="text-muted-foreground"> · p.{hit.page_number}</span>
                  )}
                </span>
              </button>
              {open && (
                <div className="mx-2 mt-1.5 mb-1 rounded-xl border border-border bg-surface-2 p-3 text-sm text-muted">
                  <p className="whitespace-pre-wrap">{hit.text}</p>
                  <a
                    href={hit.source_url}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-2 inline-flex items-center gap-1 break-all text-xs text-accent hover:underline"
                  >
                    <ExternalLink size={12} className="shrink-0" />
                    {hit.source_url}
                  </a>
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
});

export default SourceList;
