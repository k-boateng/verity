import { useState } from "react";
import type { CheckpointResult } from "../api";
import { api } from "../api";
import RichText from "./RichText";

interface Props {
  docId: string;
  sectionAnchor: string;
  sectionLabel: string;
  onClose: () => void;
}

type Phase = "ask" | "checking" | "done";

const STATUS_MARK: Record<string, string> = { hit: "✓", partial: "~", miss: "○" };

/** Active recall, not a summary. You reconstruct the section's point from
 * memory; then Verity shows the key points (grounded in the section) and
 * reflects back what landed and what slipped. Diagnostic, never a score. */
export default function CheckpointPanel({ docId, sectionAnchor, sectionLabel, onClose }: Props) {
  const [answer, setAnswer] = useState("");
  const [phase, setPhase] = useState<Phase>("ask");
  const [result, setResult] = useState<CheckpointResult | null>(null);

  const run = async (reveal: boolean) => {
    setPhase("checking");
    try {
      const res = await api.checkpoint(docId, {
        section_anchor: sectionAnchor,
        section_label: sectionLabel,
        answer: reveal ? "" : answer,
      });
      setResult(res);
    } catch (err) {
      setResult({ key_points: [], feedback: `[${(err as Error).message}]`, error: true });
    }
    setPhase("done");
  };

  return (
    <div className="checkpoint-panel">
      <div className="checkpoint-head">
        <span className="badge badge-checkpoint">Did it land?</span>
        <span className="checkpoint-section">{sectionLabel}</span>
        <button type="button" className="chat-close" onClick={onClose} aria-label="Close">
          ✕
        </button>
      </div>

      {phase === "ask" && (
        <div className="checkpoint-body">
          <p className="checkpoint-q">In a sentence or two, what was the key point of this section?</p>
          <textarea
            className="checkpoint-input"
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
            placeholder="From memory — don't scroll back up…"
            rows={3}
            autoFocus
          />
          <div className="checkpoint-actions">
            <button
              type="button"
              className="checkpoint-check"
              onClick={() => run(false)}
              disabled={!answer.trim()}
            >
              Check
            </button>
            <button type="button" className="checkpoint-reveal" onClick={() => run(true)}>
              Just show me
            </button>
          </div>
        </div>
      )}

      {phase === "checking" && <div className="checkpoint-body checkpoint-loading">Checking…</div>}

      {phase === "done" && result && (
        <div className="checkpoint-body">
          {result.feedback && (
            <p className="checkpoint-feedback">
              <RichText text={result.feedback} />
            </p>
          )}
          {result.key_points.length > 0 && (
            <ul className="checkpoint-points">
              {result.key_points.map((kp, i) => (
                <li key={i} className={`checkpoint-point status-${kp.status}`}>
                  <span className="checkpoint-mark" aria-hidden>
                    {STATUS_MARK[kp.status]}
                  </span>
                  <span className="checkpoint-point-text">
                    <RichText text={kp.point} />
                  </span>
                </li>
              ))}
            </ul>
          )}
          <div className="checkpoint-actions">
            <button type="button" className="checkpoint-check" onClick={onClose}>
              Got it
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
