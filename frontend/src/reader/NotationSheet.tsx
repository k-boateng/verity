import { useMemo, useState } from "react";
import type { GraphNode } from "../api";

interface Props {
  nodes: GraphNode[];
  onJumpTo: (node: GraphNode) => void;
}

export default function NotationSheet({ nodes, onJumpTo }: Props) {
  const [open, setOpen] = useState(true);

  const symbols = useMemo(
    () =>
      nodes
        .filter((n) => n.kind === "symbol")
        .sort((a, b) => {
          // grounded entries first, then by frequency
          const ga = a.data.grounded ? 0 : 1;
          const gb = b.data.grounded ? 0 : 1;
          if (ga !== gb) return ga - gb;
          return (b.data.count ?? 0) - (a.data.count ?? 0);
        }),
    [nodes],
  );

  if (symbols.length === 0) return null;

  return (
    <aside className={`notation-sheet ${open ? "" : "collapsed"}`}>
      <div className="notation-head">
        <h3>Notation</h3>
        <button
          type="button"
          className="notation-toggle"
          onClick={() => setOpen(!open)}
          aria-expanded={open}
        >
          {open ? "hide" : "show"}
        </button>
      </div>
      {open && (
        <ul>
          {symbols.map((s) => (
            <li key={s.id} className="notation-entry">
              <code className="notation-token">{s.label}</code>
              {s.excerpt ? (
                <span className="notation-def">
                  <code>{s.excerpt}</code>
                  {s.definition_anchor && (
                    <button
                      type="button"
                      className="notation-jump"
                      onClick={() => onJumpTo(s)}
                    >
                      →
                    </button>
                  )}
                </span>
              ) : (
                <span className="badge badge-abstain">not defined in this paper</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </aside>
  );
}
