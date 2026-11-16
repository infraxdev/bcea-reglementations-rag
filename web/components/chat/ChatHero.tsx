import { Bot } from "lucide-react";

export default function ChatHero() {
  return (
    <div className="relative flex flex-1 flex-col items-center justify-center overflow-hidden px-6 pb-4">
      <p
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-1/2 -translate-y-1/2 select-none text-center text-[20vw] leading-none font-black tracking-tight text-foreground/[0.025] sm:text-[13rem]"
      >
        BCEAO
      </p>

      <div className="relative mt-14 flex flex-col items-center sm:mt-16">
        <div
          className="animate-float-slow absolute -top-4 -left-24 hidden items-center gap-1.5 rounded-full border border-border bg-surface px-3 py-1.5 text-xs text-foreground shadow-lg sm:flex"
          style={{ animationDelay: "0.3s" }}
        >
          <span className="flex size-4 items-center justify-center rounded-full bg-gradient-to-br from-accent to-accent-2 text-accent-foreground">
            <Bot size={10} />
          </span>
          Essayez : réserves obligatoires
        </div>
        <div
          className="animate-float-slow absolute -top-10 -right-28 hidden items-center gap-1.5 rounded-full border border-border bg-surface px-3 py-1.5 text-xs text-foreground shadow-lg sm:flex"
        >
          <span className="flex size-4 items-center justify-center rounded-full bg-gradient-to-br from-accent to-accent-2 text-accent-foreground">
            <Bot size={10} />
          </span>
          Demandez les règles LBC/FT
        </div>

        <div className="flex size-20 items-center justify-center rounded-3xl bg-gradient-to-br from-accent to-accent-2 text-accent-foreground shadow-xl shadow-accent/30">
          <Bot size={36} />
        </div>
      </div>

      <h1 className="mt-6 text-center text-2xl font-semibold text-foreground sm:text-3xl">
        Ask about BCEAO regulations
      </h1>
      <p className="mt-2 max-w-sm text-center text-sm text-muted-foreground">
        Ask a question to test the retrieval and generation pipeline end to end.
      </p>
    </div>
  );
}
