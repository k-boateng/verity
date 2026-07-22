import { useCallback, useEffect, useState } from "react";

export interface SelectionSnapshot {
  text: string;
  paragraphText: string;
  sectionAnchor: string;
  nodeAnchors: string[];
  rect: DOMRect;
}

function read(): SelectionSnapshot | null {
  const sel = window.getSelection();
  if (!sel || sel.isCollapsed || sel.rangeCount === 0) return null;
  const text = sel.toString().replace(/\s+/g, " ").trim();
  if (text.length < 2) return null;

  const range = sel.getRangeAt(0);
  const common = range.commonAncestorContainer;
  const el = common.nodeType === Node.TEXT_NODE ? common.parentElement : (common as Element);
  const paper = el?.closest?.(".paper-body");
  if (!paper) return null; // only resolve selections inside the paper

  const para = el?.closest?.(".ltx_para, .ltx_p, p") ?? paper;
  const paragraphText = (para.textContent ?? "").replace(/\s+/g, " ").trim().slice(0, 1500);
  const section = el?.closest?.("section[id]") as HTMLElement | null;
  const nodeAnchors = Array.from(para.querySelectorAll("[data-verity]"))
    .map((n) => n.getAttribute("data-verity"))
    .filter((a): a is string => Boolean(a));
  const rect = range.getBoundingClientRect();
  if (rect.width === 0 && rect.height === 0) return null;

  return { text, paragraphText, sectionAnchor: section?.id ?? "", nodeAnchors, rect };
}

/** Watches for a committed text selection inside the paper and snapshots it
 * (text + surrounding paragraph + nearby resolved anchors + position), so the
 * Ask UI can act on it even after the browser selection collapses. Selections
 * or clicks inside the Ask UI itself (marked .selection-ui) are ignored. */
export function useSelection() {
  const [snapshot, setSnapshot] = useState<SelectionSnapshot | null>(null);

  const clear = useCallback(() => setSnapshot(null), []);

  useEffect(() => {
    const onUp = (event: Event) => {
      const target = event.target as Element | null;
      if (target?.closest?.(".selection-ui")) return; // don't disturb our own UI
      // let the browser finalize the selection first
      window.setTimeout(() => {
        const snap = read();
        if (snap) setSnapshot(snap);
        else if (!document.querySelector(".selection-ui:hover")) setSnapshot(null);
      }, 10);
    };
    document.addEventListener("mouseup", onUp);
    document.addEventListener("keyup", onUp);
    return () => {
      document.removeEventListener("mouseup", onUp);
      document.removeEventListener("keyup", onUp);
    };
  }, []);

  return { snapshot, clear };
}
