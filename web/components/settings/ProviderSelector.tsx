"use client";

import { ChevronDown, Cpu } from "lucide-react";
import { PROVIDERS, type Provider } from "@/lib/types";

const PROVIDER_LABEL: Record<Provider, string> = {
  default: "Server default",
  ollama: "Ollama",
  openai: "OpenAI",
  anthropic: "Anthropic",
};

export default function ProviderSelector({
  provider,
  model,
  onProviderChange,
  onModelChange,
}: {
  provider: Provider;
  model: string;
  onProviderChange: (p: Provider) => void;
  onModelChange: (m: string) => void;
}) {
  return (
    <div className="flex items-center gap-2">
      <div className="relative flex h-9 items-center gap-1.5 rounded-full border border-border bg-surface pl-3 pr-2.5 text-sm font-medium text-foreground shadow-sm">
        <Cpu size={14} className="text-accent" />
        <span className="max-w-32 truncate sm:max-w-none">{PROVIDER_LABEL[provider]}</span>
        <ChevronDown size={14} className="text-muted" />
        <select
          value={provider}
          onChange={(e) => onProviderChange(e.target.value as Provider)}
          aria-label="Model provider"
          className="absolute inset-0 h-full w-full cursor-pointer appearance-none opacity-0"
        >
          {PROVIDERS.map((p) => (
            <option key={p} value={p}>
              {PROVIDER_LABEL[p]}
            </option>
          ))}
        </select>
      </div>
      {provider !== "default" && (
        <input
          value={model}
          onChange={(e) => onModelChange(e.target.value)}
          placeholder="model override"
          className="h-9 w-32 rounded-full border border-border bg-surface px-3 text-xs text-foreground outline-none placeholder:text-muted-foreground focus:border-accent sm:w-40"
        />
      )}
    </div>
  );
}
