"use client";

import { useEffect, useRef } from "react";
import type { ConversationMessage } from "@/lib/types";
import MessageBubble from "./MessageBubble";
import ChatHero from "./ChatHero";

export default function MessageList({
  messages,
  editingId,
  onEditStart,
  onEditCancel,
  onEditSubmit,
}: {
  messages: ConversationMessage[];
  editingId: string | null;
  onEditStart: (id: string) => void;
  onEditCancel: () => void;
  onEditSubmit: (text: string) => void;
}) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  if (messages.length === 0) {
    return <ChatHero />;
  }

  // Only the most recent user prompt can be edited: editing an earlier one would
  // invalidate everything the backend generated after it in this conversation's history.
  // Editable even while its answer is still pending — submitting the edit supersedes
  // that in-flight request (see ChatWindow.send's abort handling).
  const lastUserMessage = [...messages].reverse().find((m) => m.role === "user");
  const lastMessage = messages[messages.length - 1];

  return (
    <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-6 sm:px-8">
      <div className="mx-auto flex max-w-3xl flex-col gap-4">
        {messages.map((message) => (
          <MessageBubble
            key={message.id}
            message={message}
            canEdit={message.id === lastUserMessage?.id}
            isEditing={editingId === message.id}
            onEditStart={() => onEditStart(message.id)}
            onEditCancel={onEditCancel}
            onEditSubmit={onEditSubmit}
            // Retrying re-sends the last user prompt, which only makes sense for the
            // trailing assistant turn — earlier failed turns already have a newer prompt
            // stacked on top of them in `history`.
            onRetry={
              message.id === lastMessage?.id && lastUserMessage
                ? () => onEditSubmit(lastUserMessage.content)
                : undefined
            }
          />
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
