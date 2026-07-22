import {
  autoUpdate,
  flip,
  offset,
  shift,
  useFloating,
} from "@floating-ui/react";
import { useEffect } from "react";
import type { GraphNode } from "../api";

interface Props {
  node: GraphNode;
  referenceEl: Element;
  onJump: (node: GraphNode) => void;
  onClose: () => void;
  onMouseEnter: () => void;
  onMouseLeave: () => void;
}

export default function HoverCard({
  node,
  referenceEl,
  onJump,
  onClose,
  onMouseEnter,
  onMouseLeave,
}: Props) {
  const { refs, floatingStyles } = useFloating({
    placement: "top",
    middleware: [offset(10), flip(), shift({ padding: 12 })],
    whileElementsMounted: autoUpdate,
  });

  useEffect(() => {
    refs.setReference(referenceEl);
  }, [refs, referenceEl]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const sectionLabel = node.data.section_label;
  const canJump = Boolean(node.html_anchor);

  return (
    <div
      ref={refs.setFloating}
      style={floatingStyles}
      className="hover-card"
      role="tooltip"
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
    >
      <div className="hover-card-head">
        <span className="badge badge-paper">
          From the paper{sectionLabel ? ` · ${sectionLabel}` : ""}
        </span>
        {node.label && <span className="hover-card-label">{node.label}</span>}
      </div>
      {node.data.excerpt_html ? (
        <div
          className="hover-card-body paper-voice"
          dangerouslySetInnerHTML={{ __html: node.data.excerpt_html }}
        />
      ) : (
        <div className="hover-card-body paper-voice">{node.excerpt}</div>
      )}
      {canJump && (
        <button type="button" className="jump-link" onClick={() => onJump(node)}>
          Jump to {node.label || "source"} →
        </button>
      )}
    </div>
  );
}
