import { useMemo, useState } from "react";
import type { GraphNode } from "../api";

interface Props {
  nodes: GraphNode[];
  visibleSections: Set<string>;
  onJumpTo: (node: GraphNode) => void;
}

type Scope = "in-view" | "all";

export default function NotationSheet({ nodes, visibleSections, onJumpTo }: Props) {
  const [scope, setScope] = useState<Scope>("in-view");

  const symbols = useMemo(
    () =>
      nodes
        .filter((n) => n.kind === "symbol")
        .sort((a, b) => {
          const ga = a.data.grounded ? 0 : 1;
          const gb = b.data.grounded ? 0 : 1;
          if (ga !== gb) return ga - gb;
          return (b.data.count ?? 0) - (a.data.count ?? 0);
        }),
    [nodes],
  );

  const shown = useMemo(() => {
    if (scope === "all") return symbols;
    return symbols.filter((s) => {
      const sections = s.data.sections;
      // legacy graphs without location data: never hide silently
      if (sections === undefined) return true;
      return sections.some((anchor) => visibleSections.has(anchor));
    });
  }, [symbols, scope, visibleSections]);

  if (symbols.length === 0) return null;

  return (
    <aside className="notation-sheet">
      <div className="notation-head">
        <h3>Notation</h3>
        <div className="notation-scope" role="group" aria-label="Notation scope">
          <button
            type="button"
            className={scope === "in-view" ? "active" : ""}
            onClick={() => setScope("in-view")}
            aria-pressed={scope === "in-view"}
          >
            In view
          </button>
          <button
            type="button"
            className={scope === "all" ? "active" : ""}
            onClick={() => setScope("all")}
            aria-pressed={scope === "all"}
          >
            All
          </button>
        </div>
      </div>
      {shown.length === 0 ? (
        <p className="notation-empty">No notation in the sections on screen.</p>
      ) : (
        <ul>
          {shown.map((s) => (
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
