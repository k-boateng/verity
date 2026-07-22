import { useMemo, useState } from "react";
import type { GraphNode } from "../api";

interface Props {
  nodes: GraphNode[];
  visibleSections: Set<string>;
  onJumpTo: (node: GraphNode) => void;
}

/** The definition column reflects how far resolution has gotten, and never
 * fabricates: a grounded definition is quoted, an inferred one is flagged,
 * a genuinely-undefined symbol abstains, and an unresolved one shows only
 * where it appears until the model fills it in. */
function NotationDefinition({
  node,
  onJumpTo,
}: {
  node: GraphNode;
  onJumpTo: (node: GraphNode) => void;
}) {
  const status = node.data.definition_status ?? "unresolved";

  if (status === "grounded" || status === "inferred") {
    return (
      <span className="notation-def">
        {status === "inferred" && <span className="badge badge-abstain">inferred</span>}{" "}
        {node.excerpt}
        {node.definition_anchor && (
          <button type="button" className="notation-jump" onClick={() => onJumpTo(node)}>
            →
          </button>
        )}
      </span>
    );
  }
  if (status === "undefined") {
    return <span className="badge badge-abstain">not stated in this paper</span>;
  }
  // unresolved
  const sections = node.data.sections ?? [];
  return (
    <span className="notation-loc">
      {sections.length ? `appears in ${sections.length} section${sections.length > 1 ? "s" : ""}` : "—"}
    </span>
  );
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
              {s.data.label_mathml ? (
                <span
                  className="notation-token"
                  dangerouslySetInnerHTML={{ __html: s.data.label_mathml }}
                />
              ) : (
                <code className="notation-token">{s.label}</code>
              )}
              <NotationDefinition node={s} onJumpTo={onJumpTo} />
            </li>
          ))}
        </ul>
      )}
    </aside>
  );
}
