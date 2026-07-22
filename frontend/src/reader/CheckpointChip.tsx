interface Props {
  label: string;
  onOpen: () => void;
  onDismiss: () => void;
}

/** The quiet, dismissible nudge at a section boundary. Never blocks reading —
 * it's an invitation, not a gate. */
export default function CheckpointChip({ label, onOpen, onDismiss }: Props) {
  return (
    <div className="checkpoint-chip">
      <button type="button" className="checkpoint-chip-main" onClick={onOpen}>
        <span className="checkpoint-spark">✦</span> {label} done — did it land?
      </button>
      <button
        type="button"
        className="checkpoint-chip-dismiss"
        onClick={onDismiss}
        aria-label="Dismiss checkpoint"
      >
        ✕
      </button>
    </div>
  );
}
