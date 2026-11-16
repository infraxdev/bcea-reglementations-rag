"use client";

import type { Provider } from "@/lib/types";
import ProviderSelector from "../settings/ProviderSelector";

export default function TopBar({
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
    <header className="flex items-center gap-3 px-4 py-4 sm:px-8">
      <ProviderSelector
        provider={provider}
        model={model}
        onProviderChange={onProviderChange}
        onModelChange={onModelChange}
      />
    </header>
  );
}
