import { autoUpdate, flip, offset, shift, useFloating } from "@floating-ui/react";
import { useEffect, useMemo, useState } from "react";
import type { GraphNode, ResolveResult } from "../api";
import { api } from "../api";
import type { ChatSeed } from "./ChatDock";
import RichText from "./RichText";
import type { SelectionSnapshot } from "./useSelection";

interface Props {
  docId: string;
  nodes: GraphNode[];
  llmConfigured: boolean;
  snapshot: SelectionSnapshot | null;
  onClear: () => void;
  onJumpAnchor: (label: string, anchor: string) => void;
  onOpenChat: (seed: ChatSeed) => void;
}

type Phase = "chip" | "resolving" | "resolved";

function useRectFloating(rect: DOMRect | null) {
  const floating = useFloating({
    placement: "top",
    middleware: [offset(8), flip(), shift({ padding: 10 })],
    whileElementsMounted: autoUpdate,
  });
  useEffect(() => {
    if (rect) floating.refs.setReference({ getBoundingClientRect: () => rect } as never);
  }, [rect, floating.refs]);
  return floating;
}

export default function SelectionLayer({
  docId,
  nodes,
  llmConfigured,
  snapshot,
  onClear,
  onJumpAnchor,
  onOpenChat,
}: Props) {
  const [phase, setPhase] = useState<Phase>("chip");
  const [result, setResult] = useState<ResolveResult | null>(null);

  const nodeByAnchor = useMemo(() => {
    const map = new Map<string, GraphNode>();
    for (const n of nodes) if (n.html_anchor) map.set(n.html_anchor, n);
    return map;
  }, [nodes]);

  useEffect(() => {
    setPhase("chip");
    setResult(null);
  }, [snapshot]);

  const { refs, floatingStyles } = useRectFloating(snapshot?.rect ?? null);

  if (!snapshot) return null;

  const dependencies = snapshot.nodeAnchors
    .map((anchor) => {
      const node = nodeByAnchor.get(anchor);
      if (!node) return null;
      const detail = node.excerpt ? `: ${node.excerpt.slice(0, 120)}` : ` (${node.kind})`;
      return `${node.label}${detail}`;
    })
    .filter((d): d is string => Boolean(d));

  const sectionLabel = snapshot.sectionAnchor
    ? nodeByAnchor.get(snapshot.sectionAnchor)?.label ?? ""
    : "";

  const runResolve = async () => {
    setPhase("resolving");
    try {
      const res = await api.resolve(docId, {
        selection: snapshot.text,
        paragraph: snapshot.paragraphText,
        section: sectionLabel,
        dependencies,
      });
      setResult(res);
      setPhase("resolved");
    } catch (err) {
      setResult({ mode: "generated", content: `[${(err as Error).message}]`, label: "", anchor: "" });
      setPhase("resolved");
    }
  };

  const openChat = () => {
    onOpenChat({
      paragraph: snapshot.paragraphText,
      selection: snapshot.text,
      section: sectionLabel,
      sectionAnchor: snapshot.sectionAnchor,
      dependencies,
    });
    onClear();
  };

  return (
    <div ref={refs.setFloating} style={floatingStyles} className="selection-ui">
      {phase === "chip" && (
        <button
          type="button"
          className="ask-chip"
          onClick={runResolve}
          onMouseDown={(e) => e.preventDefault()}
        >
          ✦ Explain this
        </button>
      )}

      {phase === "resolving" && <div className="ask-chip loading">Resolving…</div>}

      {phase === "resolved" && result && (
        <ResolutionCard
          result={result}
          llmConfigured={llmConfigured}
          onJump={() => result.anchor && onJumpAnchor(result.label, result.anchor)}
          onAsk={openChat}
          onClose={onClear}
        />
      )}
    </div>
  );
}

function ResolutionCard({
  result,
  llmConfigured,
  onJump,
  onAsk,
  onClose,
}: {
  result: ResolveResult;
  llmConfigured: boolean;
  onJump: () => void;
  onAsk: () => void;
  onClose: () => void;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  if (result.mode === "unconfigured") {
    return (
      <div className="resolution-card">
        <div className="rc-body">
          The paper doesn’t define this, and no model is connected yet to explain it.
          {!llmConfigured && " Add a model API key to enable explanations."}
        </div>
      </div>
    );
  }

  if (result.mode === "error") {
    return (
      <div className="resolution-card">
        <div className="rc-body">{result.content}</div>
      </div>
    );
  }

  const isRetrieved = result.mode === "retrieved";
  const isAbstained = result.mode === "abstained";

  return (
    <div className="resolution-card">
      <div className="rc-head">
        {isRetrieved ? (
          <span className="badge badge-paper">
            From the paper{result.section_label ? ` · ${result.section_label}` : ""}
          </span>
        ) : isAbstained ? (
          <span className="badge badge-abstain">Not stated in this paper</span>
        ) : (
          <span className="badge badge-ai">Explained by AI</span>
        )}
        {result.label && <span className="rc-label">{result.label}</span>}
      </div>
      <div className={`rc-body ${isRetrieved ? "paper-voice" : ""}`}>
        <RichText text={result.content} />
      </div>
      <div className="rc-actions">
        {isRetrieved && result.anchor && (
          <button type="button" className="rc-link" onClick={onJump}>
            Jump to {result.label || "source"} →
          </button>
        )}
        <button type="button" className="rc-link rc-ask" onClick={onAsk}>
          Still stuck? Ask a follow-up →
        </button>
      </div>
    </div>
  );
}
