import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import type { GraphNode } from "../api";
import { api } from "../api";
import Breadcrumb from "../reader/Breadcrumb";
import ChatDock from "../reader/ChatDock";
import type { ChatMsg, ChatSeed, ChatThread } from "../reader/ChatDock";
import ConversationsMenu from "../reader/ConversationsMenu";
import NotationSheet from "../reader/NotationSheet";
import PaperView from "../reader/PaperView";
import SelectionLayer from "../reader/SelectionLayer";
import { useDepthTrail } from "../reader/useDepthTrail";
import { useSelection } from "../reader/useSelection";

export default function Reader() {
  const { docId } = useParams<{ docId: string }>();
  const { trail, dive, popBack } = useDepthTrail();
  const [notationOpen, setNotationOpen] = useState(false);
  const [visibleSections, setVisibleSections] = useState<Set<string>>(new Set());
  const { snapshot, clear } = useSelection();

  // Chat threads live here (not in the transient selection layer) so they
  // survive a stray click and can be reopened for the rest of the session.
  const [threads, setThreads] = useState<ChatThread[]>([]);
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null);

  const cfg = useQuery({ queryKey: ["config"], queryFn: api.getConfig });

  const doc = useQuery({
    queryKey: ["document", docId],
    queryFn: () => api.getDocument(docId!),
    enabled: Boolean(docId),
  });
  const html = useQuery({
    queryKey: ["html", docId],
    queryFn: () => api.getHtml(docId!),
    enabled: Boolean(docId),
  });
  const graph = useQuery({
    queryKey: ["graph", docId],
    queryFn: () => api.getGraph(docId!),
    enabled: Boolean(docId),
  });

  const symbolCount = useMemo(
    () => graph.data?.nodes.filter((n) => n.kind === "symbol").length ?? 0,
    [graph.data],
  );

  const handleJump = (node: GraphNode) => {
    const anchor = node.definition_anchor || node.html_anchor;
    if (anchor) dive(node.label || node.kind, anchor);
  };

  const handleJumpAnchor = (label: string, anchor: string) => {
    if (anchor) dive(label || "source", anchor);
  };

  const openChat = (seed: ChatSeed) => {
    // reopen an existing thread for the same passage instead of duplicating it
    const existing = threads.find(
      (t) => t.seed.selection === seed.selection && t.seed.sectionAnchor === seed.sectionAnchor,
    );
    if (existing) {
      setActiveThreadId(existing.id);
      return;
    }
    const thread: ChatThread = { id: crypto.randomUUID(), seed, messages: [] };
    setThreads((prev) => [...prev, thread]);
    setActiveThreadId(thread.id);
  };

  const setThreadMessages = (id: string, messages: ChatMsg[]) =>
    setThreads((prev) => prev.map((t) => (t.id === id ? { ...t, messages } : t)));

  const activeThread = threads.find((t) => t.id === activeThreadId) ?? null;

  if (doc.isError || html.isError || graph.isError) {
    const err = (doc.error || html.error || graph.error) as Error;
    return (
      <div className="reader-message">
        <p className="error">{err.message}</p>
        <Link to="/">← Library</Link>
      </div>
    );
  }

  if (!doc.data || !html.data || !graph.data) {
    return <div className="reader-message">Loading…</div>;
  }

  return (
    <div className="reader">
      <nav className="reader-bar">
        <Link to="/" className="home-link" aria-label="Back to library">
          Verity
        </Link>
        <Breadcrumb title={doc.data.title} trail={trail} onPopBack={popBack} />
        {threads.length > 0 && (
          <ConversationsMenu
            threads={threads}
            activeId={activeThreadId}
            onOpen={setActiveThreadId}
          />
        )}
        {symbolCount > 0 && (
          <button
            type="button"
            className={`notation-toggle-btn ${notationOpen ? "active" : ""}`}
            onClick={() => setNotationOpen(!notationOpen)}
            aria-pressed={notationOpen}
          >
            Notation
          </button>
        )}
      </nav>
      <div className={`reader-layout ${notationOpen ? "with-notation" : ""}`}>
        <PaperView
          html={html.data}
          nodes={graph.data.nodes}
          onJump={handleJump}
          onVisibleSectionsChange={setVisibleSections}
        />
        {notationOpen && (
          <NotationSheet
            nodes={graph.data.nodes}
            visibleSections={visibleSections}
            onJumpTo={handleJump}
          />
        )}
      </div>
      <SelectionLayer
        docId={docId!}
        nodes={graph.data.nodes}
        llmConfigured={cfg.data?.llm_configured ?? false}
        snapshot={snapshot}
        onClear={clear}
        onJumpAnchor={handleJumpAnchor}
        onOpenChat={openChat}
      />
      {activeThread && (
        <ChatDock
          docId={docId!}
          thread={activeThread}
          onMessages={(m) => setThreadMessages(activeThread.id, m)}
          onClose={() => setActiveThreadId(null)}
          onJumpToPassage={(t) => t.seed.sectionAnchor && dive(t.seed.section || "passage", t.seed.sectionAnchor)}
        />
      )}
    </div>
  );
}
