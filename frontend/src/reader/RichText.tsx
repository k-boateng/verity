import katex from "katex";
import "katex/dist/katex.min.css";
import { useMemo } from "react";

// Split on $$...$$ (display) and $...$ (inline). Unclosed math mid-stream stays
// plain text until the closing delimiter arrives, so streaming doesn't flicker.
const MATH_RE = /\$\$([\s\S]+?)\$\$|\$([^$\n]+?)\$/g;

function render(tex: string, display: boolean): string {
  try {
    return katex.renderToString(tex, { displayMode: display, throwOnError: false });
  } catch {
    return display ? `$$${tex}$$` : `$${tex}$`;
  }
}

/** Renders assistant/answer text with inline and display LaTeX math. */
export default function RichText({ text }: { text: string }) {
  const parts = useMemo(() => {
    const out: { kind: "text" | "math"; value: string; display?: boolean }[] = [];
    let last = 0;
    let m: RegExpExecArray | null;
    MATH_RE.lastIndex = 0;
    while ((m = MATH_RE.exec(text)) !== null) {
      if (m.index > last) out.push({ kind: "text", value: text.slice(last, m.index) });
      if (m[1] != null) out.push({ kind: "math", value: m[1], display: true });
      else out.push({ kind: "math", value: m[2], display: false });
      last = MATH_RE.lastIndex;
    }
    if (last < text.length) out.push({ kind: "text", value: text.slice(last) });
    return out;
  }, [text]);

  return (
    <>
      {parts.map((p, i) =>
        p.kind === "text" ? (
          <span key={i}>{p.value}</span>
        ) : (
          <span key={i} dangerouslySetInnerHTML={{ __html: render(p.value, Boolean(p.display)) }} />
        ),
      )}
    </>
  );
}
