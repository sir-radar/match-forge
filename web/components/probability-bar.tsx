export function ProbabilityBar({ values, labelled = true }: { values: Record<string, number>; labelled?: boolean }) {
  const home = values.home ?? 0;
  const draw = values.draw ?? 0;
  const away = values.away ?? 0;
  const total = home + draw + away;
  if (!Number.isFinite(total) || Math.abs(total - 1) > 0.001) return <span className="unavailable">Unavailable</span>;
  return (
    <div className="probability-wrap" aria-label={`Home ${percent(home)}, draw ${percent(draw)}, away ${percent(away)}`}>
      <div className="probability-bar" aria-hidden="true">
        <span className="home" style={{ width: `${home * 100}%` }} />
        <span className="draw" style={{ width: `${draw * 100}%` }} />
        <span className="away" style={{ width: `${away * 100}%` }} />
      </div>
      {labelled && <div className="probability-labels"><span>H {percent(home)}</span><span>D {percent(draw)}</span><span>A {percent(away)}</span></div>}
    </div>
  );
}

export function percent(value: number | null | undefined) {
  return value == null ? "—" : `${(value * 100).toFixed(1)}%`;
}
