// Adapted from shadcn/ui's new-york Input; uses MatchForge color tokens.
import type { ComponentProps } from "react";

export function Input({ className = "", type, ...props }: ComponentProps<"input">) {
  return <input data-slot="input" type={type} className={`flex h-9 w-full rounded-sm border border-[var(--highest)] bg-[var(--lowest)] px-2 py-1 text-sm text-[var(--ink)] shadow-sm transition-colors placeholder:text-[var(--outline)] focus-visible:ring-2 focus-visible:ring-[var(--secondary)] disabled:cursor-not-allowed disabled:opacity-50 ${className}`} {...props} />;
}
