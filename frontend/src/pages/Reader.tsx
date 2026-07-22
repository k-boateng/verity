import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import type { Chat, ChatMessage, GraphNode } from "../api";
import { api } from "../api";
import Breadcrumb from "../reader/Breadcrumb";
import ChatDock from "../reader/ChatDock";
import type { ChatSeed } from "../reader/ChatDock";
import CheckpointChip from "../reader/CheckpointChip";
import CheckpointPanel from "../reader/CheckpointPanel";
import ConversationsMenu from "../reader/ConversationsMenu";
import NotationSheet from "../reader/NotationSheet";
import PaperView from "../reader/PaperView";
import SelectionLayer from "../reader/SelectionLayer";
import { useDepthTrail } from "../reader/useDepthTrail";
import { useReadingPosition } from "../reader/useReadingPosition";
import { useSelection } from "../reader/useSelection";

interface SectionRef {
  anchor: string;
  label: string;
}

export default function Reader() {
  const { docId } = useParams<{ docId: string }>();
  const { trail, dive, popBack } = useDepthTrail();
  const [notationOpen, setNotationOpen] = useState(false);
  const [visibleSections, setVisibleSections] = useState<Set<string>>(new Set());
  const { snapshot, clear } = useSelection();
  const queryClient = useQueryClient();

  // Chat threads live on the server; the active one is loaded into local state.
  const [activeChat, setActiveChat] = useState<Chat | null>(null);

  // "Did it land" checkpoints: an offer at a section boundary (the chip) and,
  // when engaged, the recall panel. Offered-once tracking lives in a ref.
  const [checkpointsOn, setCheckpointsOn] = useState(
    () => localStorage.getItem("verity:checkpoints") !== "off",
  );
  const [pendingCheckpoint, setPendingCheckpoint] = useState<SectionRef | null>(null);
  const [activeCheckpoint, setActiveCheckpoint] = useState<SectionRef | null>(null);
  const offeredSections = useRef<Set<string>>(new Set());

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
  const chats = useQuery({
    queryKey: ["chats", docId],
    queryFn: () => api.listChats(docId!),
    enabled: Boolean(docId),
  });

  const symbolCount = useMemo(
    () => graph.data?.nodes.filter((n) => n.kind === "symbol").length ?? 0,
    [graph.data],
  );

  // Restore the reader's spot once the paper has actually rendered.
  useReadingPosition(docId, Boolean(html.data));

  const handleJump = (node: GraphNode) => {
    const anchor = node.definition_anchor || node.html_anchor;
    if (anchor) dive(node.label || node.kind, anchor);
  };

  const handleJumpAnchor = (label: string, anchor: string) => {
    if (anchor) dive(label || "source", anchor);
  };

  const refreshChats = () => queryClient.invalidateQueries({ queryKey: ["chats", docId] });

  const openChat = async (seed: ChatSeed) => {
    const chat = await api.openChat(docId!, {
      selection: seed.selection,
      section_label: seed.section,
      section_anchor: seed.sectionAnchor,
      paragraph: seed.paragraph,
      dependencies: seed.dependencies,
    });
    setActiveChat(chat);
    refreshChats();
  };

  const reopenChat = async (chatId: number) => {
    const chat = await api.getChat(chatId);
    setActiveChat(chat);
  };

  const setActiveMessages = (messages: ChatMessage[]) =>
    setActiveChat((c) => (c ? { ...c, messages } : c));

  const defineSymbol = async (node: GraphNode) => {
    await api.defineSymbol(docId!, node.id);
    queryClient.invalidateQueries({ queryKey: ["graph", docId] });
  };

  const llmOn = cfg.data?.llm_configured ?? false;

  const handleSectionFinished = useCallback(
    (anchor: string, label: string) => {
      if (!checkpointsOn || !llmOn) return;
      if (offeredSections.current.has(anchor)) return;
      offeredSections.current.add(anchor);
      // The chip is guarded in render against showing while a panel is open,
      // so we can just queue the newest finished section unconditionally.
      setPendingCheckpoint({ anchor, label });
    },
    [checkpointsOn, llmOn],
  );

  const toggleCheckpoints = () => {
    setCheckpointsOn((on) => {
      const next = !on;
      localStorage.setItem("verity:checkpoints", next ? "on" : "off");
      if (!next) setPendingCheckpoint(null);
      return next;
    });
  };

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
        {(chats.data?.length ?? 0) > 0 && (
          <ConversationsMenu
            chats={chats.data ?? []}
            activeId={activeChat?.id ?? null}
            onOpen={reopenChat}
          />
        )}
        {llmOn && (
          <button
            type="button"
            className={`notation-toggle-btn ${checkpointsOn ? "active" : ""}`}
            onClick={toggleCheckpoints}
            aria-pressed={checkpointsOn}
            title="Offer a quick active-recall check when you finish a section"
          >
            Checkpoints
          </button>
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
          docId={docId!}
          html={html.data}
          nodes={graph.data.nodes}
          llmConfigured={llmOn}
          onJump={handleJump}
          onVisibleSectionsChange={setVisibleSections}
          onSectionFinished={handleSectionFinished}
        />
        {notationOpen && (
          <NotationSheet
            nodes={graph.data.nodes}
            visibleSections={visibleSections}
            llmConfigured={cfg.data?.llm_configured ?? false}
            onJumpTo={handleJump}
            onDefine={defineSymbol}
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
      {activeChat && (
        <ChatDock
          chat={activeChat}
          onMessages={setActiveMessages}
          onActivity={refreshChats}
          onClose={() => setActiveChat(null)}
          onJumpToPassage={(c) =>
            c.section_anchor && dive(c.section_label || "passage", c.section_anchor)
          }
        />
      )}
      {pendingCheckpoint && !activeCheckpoint && (
        <CheckpointChip
          label={pendingCheckpoint.label}
          onOpen={() => {
            setActiveCheckpoint(pendingCheckpoint);
            setPendingCheckpoint(null);
          }}
          onDismiss={() => setPendingCheckpoint(null)}
        />
      )}
      {activeCheckpoint && (
        <CheckpointPanel
          docId={docId!}
          sectionAnchor={activeCheckpoint.anchor}
          sectionLabel={activeCheckpoint.label}
          onClose={() => setActiveCheckpoint(null)}
        />
      )}
    </div>
  );
}
