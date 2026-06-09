interface Props {
  message?: string;
  hint?: string;
}

export function Loading({ message = "Loading…", hint }: Props) {
  return (
    <div className="loading">
      <div className="spinner" />
      <div>
        <div className="loading-msg">{message}</div>
        {hint && <div className="muted small">{hint}</div>}
      </div>
    </div>
  );
}
