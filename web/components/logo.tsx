export function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <svg className="logo" viewBox={compact ? "0 0 36 36" : "0 0 160 36"} role="img" aria-label="MatchForge">
      <rect width="32" height="32" y="2" rx="6" fill="#10b981" fillOpacity=".15" stroke="#10b981" strokeWidth="1.5" />
      <path d="M9 22 14 14 18 19 23 11" stroke="#10b981" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="23" cy="11" r="2" fill="#10b981" />
      <path d="M9 26h14" stroke="#10b981" strokeWidth="1.5" strokeLinecap="round" strokeDasharray="2 3" />
      {!compact && <text x="42" y="23" fontFamily="Space Grotesk, sans-serif" fontSize="17" fontWeight="700" fill="#f8fafc" letterSpacing="-.03em">Match<tspan fill="#10b981">Forge</tspan></text>}
    </svg>
  );
}
