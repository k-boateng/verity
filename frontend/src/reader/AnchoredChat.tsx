import { useRef, useState } from "react";
import { api } from "../api";

interface Props {
  docId: string;
  seed: { paragraph: string; selection: string; section: string; dependencies: string[] };
  onClose: () => void;
}

interface Msg {
  role: "user" | "assistant";
  content: string;
}

export default function AnchoredChat({ docId, seed, onClose }: Props) {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  const send = async () => {
    const text = input.trim();
    if (!text || streaming) return;
    const next: Msg[] = [...messages, { role: "user", content: text }];
    setMessages(next);
    setInput("");
    setStreaming(true);
    setMessages([...next, { role: "assistant", content: "" }]);
    try {
      let acc = "";
      for await (const piece of api.chatStream(docId, {
        messages: next,
        paragraph: seed.paragraph,
        selection: seed.selection,
        section: seed.section,
        dependencies: seed.dependencies,
      })) {
        acc += piece;
        setMessages([...next, { role: "assistant", content: acc }]);
        scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
      }
    } catch (err) {
      setMessages([...next, { role: "assistant", content: `[${(err as Error).message}]` }]);
    } finally {
      setStreaming(false);
    }
  };

  return (
    <div className="anchored-chat selection-ui">
      <div className="chat-head">
        <span className="badge badge-ai">Anchored chat</span>
        <span className="chat-anchor" title={seed.selection}>
          on “{seed.selection.slice(0, 40)}{seed.selection.length > 40 ? "…" : ""}”
        </span>
        <button type="button" className="chat-close" onClick={onClose} aria-label="Close chat">
          ✕
        </button>
      </div>
      <div className="chat-body" ref={scrollRef}>
        {messages.length === 0 && (
          <p className="chat-hint">
            This conversation is pinned to the paragraph and already knows its context. Ask a
            follow-up.
          </p>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`chat-msg ${m.role}`}>
            {m.content || (streaming && i === messages.length - 1 ? "…" : "")}
          </div>
        ))}
      </div>
      <form
        className="chat-input"
        onSubmit={(e) => {
          e.preventDefault();
          send();
        }}
      >
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about this…"
          disabled={streaming}
          autoFocus
        />
        <button type="submit" disabled={streaming || !input.trim()}>
          Send
        </button>
      </form>
    </div>
  );
}
