import { useCallback, useState } from "react";

export interface TrailEntry {
  label: string; // where the dive landed, e.g. "Lemma 2"
  anchor: string;
  returnScrollY: number; // where the reader was before the dive
}

/** The depth trail makes "climb back out without losing your spot" literal:
 * every jump pushes the previous position; popping restores it. */
export function useDepthTrail() {
  const [trail, setTrail] = useState<TrailEntry[]>([]);

  const dive = useCallback((label: string, anchor: string) => {
    const el = document.getElementById(anchor);
    if (!el) return;
    // Read the position NOW: state updaters run later (after the scroll
    // below has already moved the page), so reading scrollY inside one
    // would record the destination instead of the way back.
    const returnScrollY = window.scrollY;
    setTrail((t) => [...t, { label, anchor, returnScrollY }]);
    // Instant scroll: smooth scrolling is unreliable over long distances
    // and disorienting on a 20k-pixel jump. The flash shows where you landed.
    el.scrollIntoView({ block: "start" });
    el.classList.add("verity-flash");
    window.setTimeout(() => el.classList.remove("verity-flash"), 1600);
  }, []);

  const popBack = useCallback(() => {
    // Side effects stay out of the state updater: React may replay updaters,
    // and a DOM write inside one is silently dropped.
    const last = trail[trail.length - 1];
    if (last) {
      window.scrollTo(0, last.returnScrollY);
    }
    setTrail((t) => t.slice(0, -1));
  }, [trail]);

  const reset = useCallback(() => setTrail([]), []);

  return { trail, dive, popBack, reset };
}
