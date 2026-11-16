"use client";

import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import {
  ArrowLeftRight,
  FileText,
  Landmark,
  Mic,
  PiggyBank,
  SendHorizontal,
  ShieldCheck,
  Sparkles,
} from "lucide-react";

const SUGGESTIONS = [
  { label: "Réserves obligatoires", icon: Landmark },
  { label: "Obligations LBC/FT", icon: ShieldCheck },
  { label: "Ratios d'adéquation des fonds propres", icon: PiggyBank },
  { label: "Transferts transfrontaliers", icon: ArrowLeftRight },
  { label: "Obligations déclaratives", icon: FileText },
];

export default function MessageInput({
  onSend,
  disabled,
}: {
  onSend: (text: string) => void;
  disabled: boolean;
}) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // The textarea is disabled while an answer is pending, which drops focus. Put the
  // caret back as soon as it is usable again so the user can keep typing.
  useEffect(() => {
    if (!disabled) textareaRef.current?.focus();
  }, [disabled]);

  const submit = () => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue("");
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <div className="px-4 pb-4 sm:px-8 sm:pb-6">
      <div className="mx-auto max-w-3xl">
        <div className="rounded-3xl border border-border bg-surface/80 p-2.5 shadow-xl shadow-black/[0.03] backdrop-blur-xl dark:shadow-black/20">
          <div className="flex items-end gap-2 px-1.5 pt-1">
            <Sparkles size={16} className="mb-2.5 shrink-0 text-accent" />
            <textarea
              ref={textareaRef}
              value={value}
              onChange={(e) => setValue(e.target.value)}
              onKeyDown={onKeyDown}
              rows={1}
              placeholder="Ask a question about BCEAO regulations…"
              disabled={disabled}
              className="max-h-40 flex-1 resize-none bg-transparent py-2 text-sm text-foreground outline-none placeholder:text-muted-foreground disabled:opacity-50"
            />
          </div>
          <div className="mt-1 flex items-center justify-between gap-2 px-1">
            <div className="flex flex-wrap items-center gap-1.5">
              {SUGGESTIONS.map(({ label, icon: Icon }) => (
                <button
                  key={label}
                  type="button"
                  onClick={() => setValue(label)}
                  disabled={disabled}
                  className="hidden items-center gap-1.5 rounded-full border border-border px-2.5 py-1.5 text-xs text-muted transition-colors hover:border-border-strong hover:bg-surface-2 hover:text-foreground disabled:pointer-events-none disabled:opacity-40 sm:flex"
                >
                  <Icon size={12} />
                  {label}
                </button>
              ))}
            </div>
            <div className="flex shrink-0 items-center gap-1.5">
              <button
                type="button"
                title="Voice input not available"
                disabled
                className="flex size-9 items-center justify-center rounded-full text-muted opacity-40"
              >
                <Mic size={16} />
              </button>
              <button
                type="button"
                onClick={submit}
                disabled={disabled || !value.trim()}
                title="Send"
                aria-label="Send"
                className="flex size-9 items-center justify-center rounded-full bg-gradient-to-br from-accent to-accent-2 text-accent-foreground shadow-md shadow-accent/30 transition-opacity disabled:opacity-40 disabled:shadow-none"
              >
                <SendHorizontal size={16} />
              </button>
            </div>
          </div>
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-1.5 sm:hidden">
          {SUGGESTIONS.map(({ label, icon: Icon }) => (
            <button
              key={label}
              type="button"
              onClick={() => setValue(label)}
              disabled={disabled}
              className="flex items-center gap-1.5 rounded-full border border-border bg-surface px-2.5 py-1.5 text-xs text-muted disabled:opacity-40"
            >
              <Icon size={12} />
              {label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
