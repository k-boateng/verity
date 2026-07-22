import { autoUpdate, flip, offset, shift, useFloating } from "@floating-ui/react";
import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { ResolveMode } from "../api";
import RichText from "./RichText";

interface Props {
  docId: string;
  containerRef: React.RefObject<HTMLDivElement | null>;
  llmConfigured: boolean;
}

interface EqTarget {
  el: Element;
  latex: string;
}

interface EqResult {
  mode: ResolveMode;
  content: string;
}

const OPEN_DELAY = 180;
const CLOSE_DELAY = 300;

/** Equations are resolvable as whole objects: hover a display equation and a
 * quiet "explain" affordance appears; clicking it sends the equation's LaTeX
 * (read from the MathML) plus its context to the model. */
export default function EquationLayer({ docId, containerRef, llmConfigured }: Props) {
  const [target, setTarget] = useState<EqTarget | null>(null);
  const [result, setResult] = useState<EqResult | null>(null);
  const [loading, setLoading] = useState(false);
  const openTimer = useRef<number | undefined>(undefined);
  const closeTimer = useRef<number | undefined>(undefined);

  const { refs, floatingStyles } = useFloating({
    placement: "top-end",
    middleware: [offset(6), flip(), shift({ padding: 10 })],
    whileElementsMounted: autoUpdate,
  });

  useEffect(() => {
    if (target) refs.setReference(target.el);
  }, [target, refs]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const equationOf = (event: Event): Element | null => {
      const t = event.target as Element | null;
      // don't fight the reference-hover: skip if pointer is on a resolvable link
      if (t?.closest?.("[data-verity]")) return null;
      return t?.closest?.(".ltx_equation, .ltx_equationgroup") ?? null;
    };

    const onOver = (event: Event) => {
      const eq = equationOf(event);
      if (!eq) return;
      const math = eq.querySelector("math");
      const latex = math?.getAttribute("alttext") ?? "";
      if (!latex.trim()) return;
      window.clearTimeout(closeTimer.current);
      window.clearTimeout(openTimer.current);
      openTimer.current = window.setTimeout(() => {
        setTarget({ el: eq, latex });
        setResult(null);
      }, OPEN_DELAY);
    };

    const onOut = (event: Event) => {
      if (equationOf(event)) {
        window.clearTimeout(openTimer.current);
        closeTimer.current = window.setTimeout(() => {
          setTarget(null);
          setResult(null);
        }, CLOSE_DELAY);
      }
    };

    container.addEventListener("mouseover", onOver);
    container.addEventListener("mouseout", onOut);
    return () => {
      window.clearTimeout(openTimer.current);
      window.clearTimeout(closeTimer.current);
      container.removeEventListener("mouseover", onOver);
      container.removeEventListener("mouseout", onOut);
    };
  }, [containerRef]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setTarget(null);
        setResult(null);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  const explain = async () => {
    if (!target) return;
    setLoading(true);
    const context = collectContext(target.el);
    const symbols = collectSymbols(target.el);
    try {
      const res = await api.explainEquation(docId, { latex: target.latex, context, symbols });
      setResult(res);
    } catch (err) {
      setResult({ mode: "error", content: `[${(err as Error).message}]` });
    } finally {
      setLoading(false);
    }
  };

  const keepOpen = () => window.clearTimeout(closeTimer.current);
  const scheduleClose = () => {
    closeTimer.current = window.setTimeout(() => {
      setTarget(null);
      setResult(null);
    }, CLOSE_DELAY);
  };

  if (!target) return null;

  return (
    <div
      ref={refs.setFloating}
      style={floatingStyles}
      className="selection-ui"
      onMouseEnter={keepOpen}
      onMouseLeave={scheduleClose}
    >
      {!result && !loading && (
        <button type="button" className="ask-chip" onClick={explain}>
          ✦ Explain equation
        </button>
      )}
      {loading && <div className="ask-chip loading">Resolving…</div>}
      {result && (
        <div className="resolution-card">
          {result.mode === "unconfigured" ? (
            <div className="rc-body">
              No model is connected yet to explain this.
              {!llmConfigured && " Add a GEMINI_API_KEY to enable explanations."}
            </div>
          ) : (
            <>
              <div className="rc-head">
                <span className={`badge ${result.mode === "abstained" ? "badge-abstain" : "badge-ai"}`}>
                  {result.mode === "abstained" ? "Not stated in this paper" : "Explained by AI"}
                </span>
              </div>
              <div className="rc-body">
                <RichText text={result.content} />
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

function collectContext(eq: Element): string {
  // the surrounding section's text, so the model reads the equation in context
  let node: Element | null = eq;
  while (node) {
    const classes = node.className?.toString?.() ?? "";
    if (/ltx_(sub)*section|ltx_appendix/.test(classes)) break;
    node = node.parentElement;
  }
  const text = (node ?? eq.parentElement ?? eq).textContent ?? "";
  return text.replace(/\s+/g, " ").trim().slice(0, 1500);
}

function collectSymbols(eq: Element): string[] {
  const seen = new Set<string>();
  eq.querySelectorAll("math mi, math mo").forEach((el) => {
    const t = el.textContent?.trim();
    if (t && t.length <= 3) seen.add(t);
  });
  return Array.from(seen).slice(0, 16);
}
