import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import type { GraphNode } from "../api";
import { api } from "../api";
import Breadcrumb from "../reader/Breadcrumb";
import NotationSheet from "../reader/NotationSheet";
import PaperView from "../reader/PaperView";
import { useDepthTrail } from "../reader/useDepthTrail";

export default function Reader() {
  const { docId } = useParams<{ docId: string }>();
  const { trail, dive, popBack } = useDepthTrail();

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

  const handleJump = (node: GraphNode) => {
    const anchor = node.definition_anchor || node.html_anchor;
    if (anchor) dive(node.label || node.kind, anchor);
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
      </nav>
      <div className="reader-layout">
        <PaperView html={html.data} nodes={graph.data.nodes} onJump={handleJump} />
        <NotationSheet nodes={graph.data.nodes} onJumpTo={handleJump} />
      </div>
    </div>
  );
}
