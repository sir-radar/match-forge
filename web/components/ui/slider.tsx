"use client";

// Adapted from shadcn/ui's new-york Slider; uses MatchForge color tokens.
import * as React from "react";
import * as SliderPrimitive from "@radix-ui/react-slider";

export function Slider({ className = "", "aria-label": label, "aria-valuetext": valueText, ...props }: React.ComponentProps<typeof SliderPrimitive.Root>) {
  return <SliderPrimitive.Root data-slot="slider" className={`relative flex h-9 w-full touch-none select-none items-center ${className}`} {...props}>
    <SliderPrimitive.Track className="relative h-1.5 w-full grow overflow-hidden rounded-full bg-[var(--highest)]">
      <SliderPrimitive.Range className="absolute h-full bg-[var(--primary)]" />
    </SliderPrimitive.Track>
    <SliderPrimitive.Thumb aria-label={label} aria-valuetext={valueText} className="block size-5 rounded-full border border-[var(--primary)] bg-[var(--lowest)] shadow focus-visible:ring-2 focus-visible:ring-[var(--secondary)] disabled:pointer-events-none disabled:opacity-50" />
  </SliderPrimitive.Root>;
}
