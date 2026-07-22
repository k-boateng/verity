import { useEffect } from "react";

/** Remembers where you were in a paper. Saves scroll position to localStorage
 * (debounced) and restores it when you reopen — reading a paper across days
 * shouldn't dump you back at the top.
 *
 * Restoring fights two things: React paints before layout settles, and images
 * load late and shift the page. So we re-apply the saved position a few times
 * over the first second, and stop the moment the reader scrolls themselves. */
export function useReadingPosition(docId: string | undefined, ready: boolean) {
  useEffect(() => {
    if (!ready || !docId) return;
    const key = `verity:pos:${docId}`;
    const saved = Number(localStorage.getItem(key) || "0");

    let restoring = saved > 200;
    const restore = () => {
      if (restoring) window.scrollTo(0, saved);
    };
    const timers = [
      window.setTimeout(restore, 60),
      window.setTimeout(restore, 350),
      window.setTimeout(() => {
        restore();
        restoring = false;
      }, 1000),
    ];

    // A real user gesture ends restore immediately so we never fight them.
    const stopRestoring = () => {
      restoring = false;
    };

    // setTimeout, not requestAnimationFrame — rAF is throttled/paused when the
    // tab isn't foregrounded, which would drop saves.
    let saveTimer = 0;
    const onScroll = () => {
      if (restoring) return;
      window.clearTimeout(saveTimer);
      saveTimer = window.setTimeout(
        () => localStorage.setItem(key, String(Math.round(window.scrollY))),
        250,
      );
    };

    window.addEventListener("wheel", stopRestoring, { passive: true });
    window.addEventListener("touchstart", stopRestoring, { passive: true });
    window.addEventListener("keydown", stopRestoring);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      timers.forEach(clearTimeout);
      window.clearTimeout(saveTimer);
      window.removeEventListener("wheel", stopRestoring);
      window.removeEventListener("touchstart", stopRestoring);
      window.removeEventListener("keydown", stopRestoring);
      window.removeEventListener("scroll", onScroll);
    };
  }, [docId, ready]);
}
