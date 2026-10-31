"use client";

import type { KeyboardEvent, ReactNode } from "react";

export function TableScroll({ label, children }: { label: string; children: ReactNode }) {
  const scroll = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.target !== event.currentTarget || !["ArrowLeft", "ArrowRight"].includes(event.key)) return;
    event.preventDefault();
    event.currentTarget.scrollLeft += (event.key === "ArrowRight" ? 1 : -1) * event.currentTarget.clientWidth / 2;
  };
  return <div className="table-scroll" tabIndex={0} role="region" aria-label={label} onKeyDown={scroll}>{children}</div>;
}
