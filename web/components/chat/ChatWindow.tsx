"use client";

import { useRef, useState } from "react";
import { ApiError, postQuery } from "@/lib/api";
import type { ChatTurn, ConversationMessage, Provider } from "@/lib/types";
import MessageList from "./MessageList";
import MessageInput from "./MessageInput";
import Sidebar from "../layout/Sidebar";
import TopBar from "../layout/TopBar";

let nextId = 0;
const newId = () => `${Date.now()}-${nextId++}`;

export default function ChatWindow() {
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [provider, setProvider] = useState<Provider>("default");
  const [model, setModel] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const pending = messages.some((m) => m.pending);

  // Backend-authoritative conversation state, distinct from `messages` (which is the
  // full on-screen transcript). The server caps `history` and folds anything older into
  // `history_summary` (see app/generation/memory.py) — we resend exactly what it last
  // returned rather than replaying every on-screen message every request.
  const [apiHistory, setApiHistory] = useState<ChatTurn[]>([]);
  const [apiHistorySummary, setApiHistorySummary] = useState<string | null>(null);

  // Snapshot of apiHistory/apiHistorySummary from just before the most recent turn was
  // sent, so an edit-and-resend of that turn can replay against the same base the
  // original request used, rather than a state that already includes its own answer.
  const [historyBaseline, setHistoryBaseline] = useState<{
    history: ChatTurn[];
    summary: string | null;
  }>({ history: [], summary: null });

  // Tracks the in-flight request so editing-and-resending the last prompt (which can
  // happen while its original answer is still pending) aborts the superseded request
  // instead of letting it race the new one and clobber apiHistory when it lands late.
  const activeRequestRef = useRef<AbortController | null>(null);

  const send = async (text: string, options?: { replaceLastTurn?: boolean }) => {
    const replacing = options?.replaceLastTurn ?? false;
    const baseHistory = replacing ? historyBaseline.history : apiHistory;
    const baseSummary = replacing ? historyBaseline.summary : apiHistorySummary;

    activeRequestRef.current?.abort(new DOMException("Superseded by a newer request", "AbortError"));
    const controller = new AbortController();
    activeRequestRef.current = controller;

    const userMessage: ConversationMessage = { id: newId(), role: "user", content: text };
    const assistantMessage: ConversationMessage = {
      id: newId(),
      role: "assistant",
      content: "",
      pending: true,
    };
    setMessages((prev) => [...(replacing ? prev.slice(0, -2) : prev), userMessage, assistantMessage]);
    setHistoryBaseline({ history: baseHistory, summary: baseSummary });
    setEditingId(null);

    const startedAt = performance.now();
    try {
      const result = await postQuery(
        {
          query: text,
          history: baseHistory,
          history_summary: baseSummary,
          provider: provider === "default" ? undefined : provider,
          model: model.trim() || undefined,
        },
        controller.signal,
      );
      const latencyMs = performance.now() - startedAt;
      setApiHistory(result.history);
      setApiHistorySummary(result.history_summary);
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantMessage.id
            ? { ...m, pending: false, content: result.answer, result, latencyMs }
            : m,
        ),
      );
    } catch (err) {
      if (err instanceof Error && err.name === "AbortError") return;
      const offline = err instanceof ApiError && err.status === 0;
      const message =
        err instanceof ApiError
          ? err.status === 501
            ? `Not configured yet: ${err.message}`
            : err.message
          : "Something went wrong sending that query.";
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantMessage.id
            ? { ...m, pending: false, error: message, errorKind: offline ? "offline" : undefined }
            : m,
        ),
      );
    } finally {
      // Only clear if we're still the current request — a superseding call already
      // overwrote the ref with its own controller, so clearing here would let a later,
      // unrelated abort() no-op against a controller whose request has already settled.
      if (activeRequestRef.current === controller) {
        activeRequestRef.current = null;
      }
    }
  };

  const clear = () => {
    activeRequestRef.current?.abort(new DOMException("Chat cleared", "AbortError"));
    setMessages([]);
    setApiHistory([]);
    setApiHistorySummary(null);
    setHistoryBaseline({ history: [], summary: null });
    setEditingId(null);
  };

  const editLastPrompt = (text: string) => {
    send(text, { replaceLastTurn: true });
  };

  return (
    <div className="flex min-h-0 flex-1">
      <Sidebar onNewChat={clear} onClearChat={clear} hasMessages={messages.length > 0} />
      <div className="flex min-h-0 flex-1 flex-col">
        <TopBar
          provider={provider}
          model={model}
          onProviderChange={setProvider}
          onModelChange={setModel}
        />
        <MessageList
          messages={messages}
          editingId={editingId}
          onEditStart={setEditingId}
          onEditCancel={() => setEditingId(null)}
          onEditSubmit={editLastPrompt}
        />
        <MessageInput onSend={send} disabled={pending || editingId != null} />
      </div>
    </div>
  );
}
