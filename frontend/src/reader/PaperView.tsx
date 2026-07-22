import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { GraphNode } from "../api";
import EquationLayer from "./EquationLayer";
import HoverCard from "./HoverCard";

interface Props {
  docId: string;
  html: string;
  nodes: GraphNode[];
  llmConfigured: boolean;
  onJump: (node: GraphNode) => void;
  onVisibleSectionsChange?: (visible: Set<string>) => void;
  onSectionFinished?: (anchor: string, label: string) => void;
}

interface HoverState {
  node: GraphNode;
  element: Element;
}

// The hover mechanic: rest ~120ms on a dotted object to open; the card
// stays while the pointer is over the object or the card, with a 300ms
// grace period to cross the gap; Esc or moving away closes; click dives.
const OPEN_DELAY_MS = 120;
const CLOSE_DELAY_MS = 300;

export default function PaperView({
  docId,
  html,
  nodes,
  llmConfigured,
  onJump,
  onVisibleSectionsChange,
  onSectionFinished,
}: Props) {
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

  // Track which sections are on screen so the notation sheet can show only
  // the symbols the reader is actually looking at. Plain rect checks on
  // scroll (plus a slow polling fallback for environments that suppress
  // scroll events) — IntersectionObserver is unreliable in throttled or
  // embedded renderers.
  useEffect(() => {
    const container = containerRef.current;
    if (!container || !onVisibleSectionsChange) return;
    const sections = Array.from(container.querySelectorAll<HTMLElement>("section[id]"));
    if (sections.length === 0) return;

    let lastKey = "";
    const compute = () => {
      const margin = 120;
      const vh = window.innerHeight;
      const visible = new Set<string>();
      for (const s of sections) {
        const r = s.getBoundingClientRect();
        if (r.bottom > -margin && r.top < vh + margin) visible.add(s.id);
      }
      const key = [...visible].sort().join(",");
      if (key !== lastKey) {
        lastKey = key;
        onVisibleSectionsChange(visible);
      }
    };

    compute();
    let lastY = window.scrollY;
    const onScroll = () => compute();
    const poll = window.setInterval(() => {
      if (window.scrollY !== lastY) {
        lastY = window.scrollY;
        compute();
      }
    }, 500);
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      window.clearInterval(poll);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    };
  }, [html, onVisibleSectionsChange]);

  // A checkpoint fires when a top-level section's end scrolls off the top —
  // you've finished reading it. We seed the already-past sections 1.3s in (so
  // a restored deep scroll position doesn't fire a backlog) and only report
  // sections crossed during this session, once each.
  useEffect(() => {
    const container = containerRef.current;
    if (!container || !onSectionFinished) return;
    const sections = Array.from(
      container.querySelectorAll<HTMLElement>(
        "section.ltx_section[id], section.ltx_appendix[id]",
      ),
    );
    if (sections.length === 0) return;

    const THRESHOLD = 120;
    const isPast = (el: HTMLElement) => el.getBoundingClientRect().bottom < THRESHOLD;
    const finished = new Set<string>();
    let active = false;

    const labelFor = (s: HTMLElement) => {
      const title = s.querySelector(":scope > .ltx_title");
      const tag = title?.querySelector(".ltx_tag")?.textContent?.trim().replace(/\.\s*$/, "");
      if (tag) return `§${tag}`;
      return title?.textContent?.trim().slice(0, 40) || s.id;
    };

    const seed = window.setTimeout(() => {
      sections.forEach((s) => {
        if (isPast(s)) finished.add(s.id);
      });
      active = true;
    }, 1300);

    const check = () => {
      if (!active) return;
      for (const s of sections) {
        if (finished.has(s.id)) continue;
        if (isPast(s)) {
          finished.add(s.id);
          onSectionFinished(s.id, labelFor(s));
        }
      }
    };

    window.addEventListener("scroll", check, { passive: true });
    return () => {
      window.clearTimeout(seed);
      window.removeEventListener("scroll", check);
    };
  }, [html, onSectionFinished]);

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
      <EquationLayer docId={docId} containerRef={containerRef} llmConfigured={llmConfigured} />
    </div>
  );
}
