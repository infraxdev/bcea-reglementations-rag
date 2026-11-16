import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { Bot, Check, Pencil, RefreshCw, WifiOff, X } from "lucide-react";
import type { ConversationMessage } from "@/lib/types";
import SourceList, { type NumberedSource, type SourceListHandle } from "./SourceList";
import MessageText, { getCitedIndices } from "./MessageText";

function TypingDots() {
  return (
    <span className="inline-flex gap-1 py-1">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground"
          style={{ animationDelay: `${i * 120}ms` }}
        />
      ))}
    </span>
  );
}

export default function MessageBubble({
  message,
  canEdit = false,
  isEditing = false,
  onEditStart,
  onEditCancel,
  onEditSubmit,
  onRetry,
}: {
  message: ConversationMessage;
  canEdit?: boolean;
  isEditing?: boolean;
  onEditStart?: () => void;
  onEditCancel?: () => void;
  onEditSubmit?: (text: string) => void;
  onRetry?: () => void;
}) {
  const isUser = message.role === "user";
  const result = message.result;
  const sourceListRef = useRef<SourceListHandle>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [draft, setDraft] = useState(message.content);
  const [wasEditing, setWasEditing] = useState(isEditing);
  if (isEditing !== wasEditing) {
    setWasEditing(isEditing);
    if (isEditing) setDraft(message.content);
  }

  useEffect(() => {
    if (!isEditing) return;
    const el = textareaRef.current;
    el?.focus();
    el?.setSelectionRange(el.value.length, el.value.length);
  }, [isEditing]);

  // Only the sources the answer actually cites, numbered to match its inline [n] chips —
  // not every candidate the retriever returned.
  // Answers that aren't grounded in the documents (general finance knowledge, or an
  // out-of-scope refusal) get a slightly tinted bubble instead of a label. Courtesy
  // replies and messages saved before `route` existed keep the normal one.
  const ungrounded = result?.route === "general_finance" || result?.route === "out_of_scope";

  const citedSources: NumberedSource[] = result
    ? getCitedIndices(message.content)
        .map((number) => ({ number, hit: result.sources[number - 1] }))
        .filter((s): s is NumberedSource => s.hit != null)
    : [];

  const submitEdit = () => {
    const trimmed = draft.trim();
    if (!trimmed) return;
    onEditSubmit?.(trimmed);
  };

  const onDraftKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submitEdit();
    } else if (e.key === "Escape") {
      onEditCancel?.();
    }
  };

  if (isUser && isEditing) {
    return (
      <div className="flex items-end justify-end gap-2">
        <div className="w-full max-w-[85%] rounded-2xl border border-border bg-surface p-2 shadow-sm sm:max-w-[75%]">
          <textarea
            ref={textareaRef}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={onDraftKeyDown}
            rows={Math.min(8, Math.max(1, draft.split("\n").length))}
            className="w-full resize-none bg-transparent px-2 py-1.5 text-sm leading-relaxed text-foreground outline-none"
          />
          <div className="flex justify-end gap-1.5 px-1 pb-1">
            <button
              type="button"
              onClick={onEditCancel}
              title="Cancel"
              aria-label="Cancel edit"
              className="flex size-7 items-center justify-center rounded-full text-muted hover:bg-surface-2 hover:text-foreground"
            >
              <X size={14} />
            </button>
            <button
              type="button"
              onClick={submitEdit}
              disabled={!draft.trim()}
              title="Save & resend"
              aria-label="Save and resend"
              className="flex size-7 items-center justify-center rounded-full bg-gradient-to-br from-accent to-accent-2 text-accent-foreground disabled:opacity-40"
            >
              <Check size={14} />
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={`group flex items-end gap-2 ${isUser ? "justify-end" : "justify-start"}`}>
      {!isUser && (
        <div className="mb-0.5 flex size-7 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-accent to-accent-2 text-accent-foreground">
          <Bot size={14} />
        </div>
      )}
      {isUser && canEdit && !message.pending && (
        <button
          type="button"
          onClick={onEditStart}
          title="Edit message"
          aria-label="Edit message"
          className="mb-0.5 flex size-7 shrink-0 items-center justify-center rounded-full text-muted opacity-0 transition-opacity hover:bg-surface-2 hover:text-foreground group-hover:opacity-100"
        >
          <Pencil size={13} />
        </button>
      )}
      <div
        className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-sm sm:max-w-[75%] ${
          isUser
            ? "rounded-br-md bg-gradient-to-br from-accent to-accent-2 text-accent-foreground"
            : `rounded-bl-md border text-foreground ${
                ungrounded ? "border-accent/25 bg-accent/[0.07]" : "border-border bg-surface"
              }`
        }`}
      >
        {message.pending ? (
          <TypingDots />
        ) : message.error ? (
          message.errorKind === "offline" ? (
            <div className="flex flex-col gap-2">
              <div className="flex items-center gap-2 font-medium text-amber-700 dark:text-amber-400">
                <WifiOff size={15} className="shrink-0" />
                Backend unavailable
              </div>
              <p className="text-muted-foreground">
                The BCEAO RAG server isn&apos;t responding right now. It may still be
                starting up or briefly offline — please try again in a moment.
              </p>
              {onRetry && (
                <button
                  type="button"
                  onClick={onRetry}
                  className="mt-1 flex w-fit items-center gap-1.5 rounded-full border border-border-strong px-3 py-1.5 text-xs font-medium text-foreground transition-colors hover:bg-surface-2"
                >
                  <RefreshCw size={12} />
                  Try again
                </button>
              )}
            </div>
          ) : (
            <p className="text-red-500 dark:text-red-400">{message.error}</p>
          )
        ) : (
          <>
            {result ? (
              <MessageText
                content={message.content}
                sources={result.sources}
                onCitationSelect={(chunkId) => sourceListRef.current?.focus(chunkId)}
              />
            ) : (
              <p className="whitespace-pre-wrap">{message.content}</p>
            )}
            {result && result.policy && !result.policy.passed && (
              <div className="mt-2 rounded-md bg-red-50 px-2.5 py-1.5 text-xs text-red-700 dark:bg-red-950/40 dark:text-red-400">
                <p className="font-medium">Policy gate flagged this answer:</p>
                <ul className="ml-3.5 list-disc">
                  {result.policy.violations.map((v) => (
                    <li key={v}>{v}</li>
                  ))}
                </ul>
              </div>
            )}
            {result && <SourceList ref={sourceListRef} sources={citedSources} />}
            {message.latencyMs != null && (
              <p
                className={`mt-2 text-right text-[11px] ${
                  isUser ? "text-accent-foreground/70" : "text-muted-foreground"
                }`}
              >
                {(message.latencyMs / 1000).toFixed(1)}s
              </p>
            )}
          </>
        )}
      </div>
    </div>
  );
}
