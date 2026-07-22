import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { GraphNode } from "../api";
import HoverCard from "./HoverCard";

interface Props {
  html: string;
  nodes: GraphNode[];
  onJump: (node: GraphNode) => void;
}

interface HoverState {
  node: GraphNode;
  element: Element;
}

const OPEN_DELAY_MS = 150;
const CLOSE_DELAY_MS = 250;

export default function PaperView({ html, nodes, onJump }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<HoverState | null>(null);
  const openTimer = useRef<number | undefined>(undefined);
  const closeTimer = useRef<number | undefined>(undefined);

  const nodeByAnchor = useMemo(() => {
    const map = new Map<string, GraphNode>();
    for (const n of nodes) {
      if (n.html_anchor) map.set(n.html_anchor, n);
    }
    return map;
  }, [nodes]);

  const cancelTimers = () => {
    window.clearTimeout(openTimer.current);
    window.clearTimeout(closeTimer.current);
  };

  const scheduleClose = useCallback(() => {
    window.clearTimeout(closeTimer.current);
    closeTimer.current = window.setTimeout(() => setHover(null), CLOSE_DELAY_MS);
  }, []);

  const cancelClose = useCallback(() => {
    window.clearTimeout(closeTimer.current);
  }, []);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const resolveTarget = (event: Event): { el: Element; node: GraphNode } | null => {
      const target = event.target as Element | null;
      const el = target?.closest?.("[data-verity]");
      if (!el) return null;
      const anchor = el.getAttribute("data-verity");
      const node = anchor ? nodeByAnchor.get(anchor) : undefined;
      return node ? { el, node } : null;
    };

    const onOver = (event: Event) => {
      const hit = resolveTarget(event);
      if (!hit) return;
      cancelTimers();
      openTimer.current = window.setTimeout(
        () => setHover({ node: hit.node, element: hit.el }),
        OPEN_DELAY_MS,
      );
    };

    const onOut = (event: Event) => {
      if (resolveTarget(event)) {
        window.clearTimeout(openTimer.current);
        scheduleClose();
      }
    };

    // Clicking a resolvable link becomes a tracked dive instead of a bare
    // anchor navigation, so the breadcrumb always knows the way back.
    const onClick = (event: Event) => {
      const hit = resolveTarget(event);
      if (!hit) return;
      event.preventDefault();
      setHover(null);
      onJump(hit.node);
    };

    const onFocusIn = (event: Event) => {
      const hit = resolveTarget(event);
      if (hit) setHover({ node: hit.node, element: hit.el });
    };

    container.addEventListener("mouseover", onOver);
    container.addEventListener("mouseout", onOut);
    container.addEventListener("click", onClick);
    container.addEventListener("focusin", onFocusIn);
    return () => {
      cancelTimers();
      container.removeEventListener("mouseover", onOver);
      container.removeEventListener("mouseout", onOut);
      container.removeEventListener("click", onClick);
      container.removeEventListener("focusin", onFocusIn);
    };
  }, [nodeByAnchor, onJump, scheduleClose]);

  return (
    <div className="paper-container">
      <div
        ref={containerRef}
        className="paper-voice paper-body"
        dangerouslySetInnerHTML={{ __html: html }}
      />
      {hover && (
        <HoverCard
          node={hover.node}
          referenceEl={hover.element}
          onJump={(node) => {
            setHover(null);
            onJump(node);
          }}
          onClose={() => setHover(null)}
          onMouseEnter={cancelClose}
          onMouseLeave={scheduleClose}
        />
      )}
    </div>
  );
}
