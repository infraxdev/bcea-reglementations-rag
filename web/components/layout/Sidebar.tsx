"use client";

import { Bot, Compass, History, Image as ImageIcon, Plus, Search, Trash2 } from "lucide-react";
import ThemeToggle from "./ThemeToggle";

function DockButton({
  icon,
  label,
  onClick,
  disabled,
}: {
  icon: React.ReactNode;
  label: string;
  onClick?: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      onClick={onClick}
      disabled={disabled}
      className="flex size-10 items-center justify-center rounded-full text-muted transition-colors hover:bg-surface-2 hover:text-foreground disabled:pointer-events-none disabled:opacity-30"
    >
      {icon}
    </button>
  );
}

export default function Sidebar({
  onNewChat,
  onClearChat,
  hasMessages,
}: {
  onNewChat: () => void;
  onClearChat: () => void;
  hasMessages: boolean;
}) {
  return (
    <aside className="flex w-16 shrink-0 flex-col items-center justify-between border-r border-border py-4">
      <div className="flex flex-col items-center gap-2">
        <div className="mb-2 flex size-10 items-center justify-center rounded-full bg-gradient-to-br from-accent to-accent-2 text-accent-foreground shadow-lg shadow-accent/30">
          <Bot size={20} />
        </div>
        <DockButton icon={<Plus size={18} />} label="New chat" onClick={onNewChat} />
        <DockButton icon={<Search size={18} />} label="Search (coming soon)" disabled />
        <DockButton icon={<Compass size={18} />} label="Explore (coming soon)" disabled />
        <DockButton icon={<ImageIcon size={18} />} label="Media (coming soon)" disabled />
        <DockButton icon={<History size={18} />} label="History (coming soon)" disabled />
      </div>
      <div className="flex flex-col items-center gap-2">
        <ThemeToggle />
        <DockButton
          icon={<Trash2 size={18} />}
          label="Clear conversation"
          onClick={onClearChat}
          disabled={!hasMessages}
        />
      </div>
    </aside>
  );
}
