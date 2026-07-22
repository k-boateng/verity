import { useEffect, useRef, useState } from "react";
import type { ChatSummary } from "../api";

interface Props {
  chats: ChatSummary[];
  activeId: number | null;
  onOpen: (id: number) => void;
}

/** Reopener for saved conversations on this paper — the permanence that
 * keeps a stray click (or a reload) from losing a thread. */
export default function ConversationsMenu({ chats, activeId, onOpen }: Props) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  return (
    <div className="conversations" ref={ref}>
      <button
        type="button"
        className={`conversations-btn ${open ? "active" : ""}`}
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        Chats ({chats.length})
      </button>
      {open && (
        <ul className="conversations-menu">
          {chats.map((c) => (
            <li key={c.id}>
              <button
                type="button"
                className={c.id === activeId ? "active" : ""}
                onClick={() => {
                  onOpen(c.id);
                  setOpen(false);
                }}
              >
                <span className="conv-quote">
                  “{c.selection.slice(0, 40)}{c.selection.length > 40 ? "…" : ""}”
                </span>
                <span className="conv-meta">
                  {c.section_label || "—"} · {c.question_count} Q
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
