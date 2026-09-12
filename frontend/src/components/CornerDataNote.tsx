export function CornerDataNote() {
  return (
    <div className="mt-3 rounded-panel border border-border p-3">
      <p className="text-xs text-muted">
        Corner data isn&apos;t available for this circuit. Its layout couldn&apos;t be resolved from
        session telemetry, so corner-based figures are left blank instead of guessed.
      </p>
    </div>
  )
}
