export function ResourceError({ message, retry }: { message: string; retry: () => void }) {
  return <div className="resource-state" role="alert"><strong>Data unavailable</strong><span>{message}</span><button onClick={retry}>Retry</button></div>;
}

export function ResourceLoading({ label }: { label: string }) {
  return <div className="resource-state loading" role="status"><span className="skeleton" />{label}</div>;
}

export function EmptyState({ title, detail }: { title: string; detail: string }) {
  return <div className="resource-state"><strong>{title}</strong><span>{detail}</span></div>;
}
