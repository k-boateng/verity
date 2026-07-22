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
    setTrail((t) => [...t, { label, anchor, returnScrollY: window.scrollY }]);
    const el = document.getElementById(anchor);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, []);

  const popBack = useCallback(() => {
    setTrail((t) => {
      const last = t[t.length - 1];
      if (last) {
        window.scrollTo({ top: last.returnScrollY, behavior: "smooth" });
      }
      return t.slice(0, -1);
    });
  }, []);

  const reset = useCallback(() => setTrail([]), []);

  return { trail, dive, popBack, reset };
}
