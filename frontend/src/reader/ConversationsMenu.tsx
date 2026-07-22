import { useEffect, useRef, useState } from "react";
import type { ChatThread } from "./ChatDock";

interface Props {
  threads: ChatThread[];
  activeId: string | null;
  onOpen: (id: string) => void;
}

/** A small reopener for chats started this session — the permanence that
 * keeps a stray click from losing a conversation. */
export default function ConversationsMenu({ threads, activeId, onOpen }: Props) {
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
        Chats ({threads.length})
      </button>
      {open && (
        <ul className="conversations-menu">
          {threads.map((t) => (
            <li key={t.id}>
              <button
                type="button"
                className={t.id === activeId ? "active" : ""}
                onClick={() => {
                  onOpen(t.id);
                  setOpen(false);
                }}
              >
                <span className="conv-quote">“{t.seed.selection.slice(0, 40)}{t.seed.selection.length > 40 ? "…" : ""}”</span>
                <span className="conv-meta">
                  {t.seed.section || "—"} · {t.messages.filter((m) => m.role === "user").length} Q
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
