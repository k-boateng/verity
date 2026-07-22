import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import RichText from "./RichText";

export interface ChatMsg {
  role: "user" | "assistant";
  content: string;
}

export interface ChatSeed {
  paragraph: string;
  selection: string;
  section: string;
  sectionAnchor: string;
  dependencies: string[];
}

export interface ChatThread {
  id: string;
  seed: ChatSeed;
  messages: ChatMsg[];
}

interface Props {
  docId: string;
  thread: ChatThread;
  onMessages: (messages: ChatMsg[]) => void;
  onClose: () => void;
  onJumpToPassage: (thread: ChatThread) => void;
}

/** The escape-hatch conversation. Docked (stable, roomy), sticky (only ✕
 * closes it — never a stray click), and its messages live in the parent so
 * the thread survives being closed and can be reopened. */
export default function ChatDock({ docId, thread, onMessages, onClose, onJumpToPassage }: Props) {
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  const messages = thread.messages;

  const grow = () => {
    const ta = textareaRef.current;
    if (ta) {
      ta.style.height = "auto";
      ta.style.height = `${Math.min(ta.scrollHeight, 160)}px`;
    }
  };

  useEffect(() => {
    bodyRef.current?.scrollTo({ top: bodyRef.current.scrollHeight });
  }, [messages]);

  const send = async () => {
    const text = input.trim();
    if (!text || streaming) return;
    const base: ChatMsg[] = [...messages, { role: "user", content: text }];
    onMessages(base);
    setInput("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
    setStreaming(true);
    try {
      let acc = "";
      onMessages([...base, { role: "assistant", content: "" }]);
      for await (const piece of api.chatStream(docId, {
        messages: base,
        paragraph: thread.seed.paragraph,
        selection: thread.seed.selection,
        section: thread.seed.section,
        dependencies: thread.seed.dependencies,
      })) {
        acc += piece;
        onMessages([...base, { role: "assistant", content: acc }]);
      }
    } catch (err) {
      onMessages([...base, { role: "assistant", content: `[${(err as Error).message}]` }]);
    } finally {
      setStreaming(false);
    }
  };

  return (
    <div className="chat-dock selection-ui">
      <div className="chat-head">
        <span className="badge badge-ai">Anchored chat</span>
        <button
          type="button"
          className="chat-anchor"
          title="Jump to the passage this is anchored to"
          onClick={() => onJumpToPassage(thread)}
        >
          on “{thread.seed.selection.slice(0, 44)}
          {thread.seed.selection.length > 44 ? "…" : ""}”
        </button>
        <button type="button" className="chat-close" onClick={onClose} aria-label="Close chat">
          ✕
        </button>
      </div>
      <div className="chat-body" ref={bodyRef}>
        {messages.length === 0 && (
          <p className="chat-hint">
            This conversation is pinned to the passage and already knows its context. Ask a
            follow-up — it stays open until you close it.
          </p>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`chat-msg ${m.role}`}>
            {m.content ? (
              <RichText text={m.content} />
            ) : streaming && i === messages.length - 1 ? (
              <span className="chat-typing">…</span>
            ) : null}
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
        <textarea
          ref={textareaRef}
          value={input}
          rows={1}
          onChange={(e) => {
            setInput(e.target.value);
            grow();
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send();
            }
          }}
          placeholder="Ask about this…  (Enter to send, Shift+Enter for a new line)"
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
