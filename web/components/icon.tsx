import type { ReactNode } from "react";

type IconName =
  | "analytics"
  | "calendar"
  | "chevron-down"
  | "chevron-left"
  | "chevron-right"
  | "chevron-up"
  | "monitoring"
  | "person"
  | "science"
  | "search"
  | "table"
  | "verified";

const paths: Record<IconName, ReactNode> = {
  analytics: <><path d="M4 19V9" /><path d="M10 19V5" /><path d="M16 19v-7" /><path d="M22 19V3" /></>,
  calendar: <><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M16 3v4M8 3v4M3 10h18M7 14h3M14 14h3M7 18h3" /></>,
  "chevron-down": <path d="m7 9 5 5 5-5" />,
  "chevron-left": <path d="m15 18-6-6 6-6" />,
  "chevron-right": <path d="m9 18 6-6-6-6" />,
  "chevron-up": <path d="m7 15 5-5 5 5" />,
  monitoring: <><path d="m3 17 5-5 4 4 8-9" /><path d="M15 7h5v5" /></>,
  person: <><circle cx="12" cy="8" r="3.5" /><path d="M5 21a7 7 0 0 1 14 0Z" /></>,
  science: <><path d="M9 3h6M10 3v6l-5 9a2 2 0 0 0 1.8 3h10.4a2 2 0 0 0 1.8-3l-5-9V3" /><path d="M8 15h8" /></>,
  search: <><circle cx="11" cy="11" r="7" /><path d="m20 20-4-4" /></>,
  table: <><rect x="3" y="4" width="18" height="16" rx="1" /><path d="M3 9h18M9 9v11M15 9v11" /></>,
  verified: <><path d="M12 3 5 6v5c0 4.6 2.9 8.3 7 10 4.1-1.7 7-5.4 7-10V6Z" /><path d="m9 12 2 2 4-4" /></>,
};

export function Icon({ name, className = "" }: { name: IconName; className?: string }) {
  return (
    <svg
      aria-hidden="true"
      className={`icon ${className}`.trim()}
      data-icon={name}
      fill="none"
      focusable="false"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth="1.8"
      viewBox="0 0 24 24"
      width="16"
      height="16"
    >
      {paths[name]}
    </svg>
  );
}
