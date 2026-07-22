import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import type { DocumentSummary } from "../api";
import { api } from "../api";

function relativeTime(iso: string | null): string {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  const secs = Math.max(0, Math.round((Date.now() - then) / 1000));
  if (secs < 60) return "just now";
  const mins = Math.round(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.round(hrs / 24);
  return `${days}d ago`;
}

export default function Home() {
  const [input, setInput] = useState("");
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const docs = useQuery({ queryKey: ["documents"], queryFn: api.listDocuments });

  const ingest = useMutation({
    mutationFn: api.ingest,
    onSuccess: (doc) => {
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      if (doc.status === "ready") navigate(`/read/${doc.id}`);
    },
  });

  return (
    <div className="home">
      <header className="home-hero">
        <h1>Verity</h1>
        <p className="tagline">Read hard papers without losing your place.</p>
        <form
          className="ingest-form"
          onSubmit={(e) => {
            e.preventDefault();
            if (input.trim() && !ingest.isPending) ingest.mutate(input.trim());
          }}
        >
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Paste an arXiv link or id — e.g. 1706.03762"
            aria-label="arXiv link or id"
            disabled={ingest.isPending}
          />
          <button type="submit" disabled={ingest.isPending || !input.trim()}>
            {ingest.isPending ? "Fetching & parsing…" : "Open"}
          </button>
        </form>
        {ingest.isPending && (
          <p className="hint">
            Fetching the paper and building its structure — usually well under a minute.
          </p>
        )}
        {ingest.isError && <p className="error">{(ingest.error as Error).message}</p>}
      </header>

      <section className="library">
        <h2>Library</h2>
        {docs.isLoading && <p className="hint">Loading your library…</p>}
        {docs.isError && <p className="error">Couldn’t load the library.</p>}
        {docs.data && docs.data.length === 0 && (
          <p className="hint">Nothing here yet — open your first paper above.</p>
        )}
        <ul>
          {docs.data?.map((d) => (
            <LibraryRow key={d.id} doc={d} onRetry={() => ingest.mutate(d.arxiv_id)} />
          ))}
        </ul>
      </section>
    </div>
  );
}

function LibraryRow({ doc, onRetry }: { doc: DocumentSummary; onRetry: () => void }) {
  const queryClient = useQueryClient();
  const [confirming, setConfirming] = useState(false);

  const del = useMutation({
    mutationFn: () => api.deleteDocument(doc.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["documents"] }),
  });

  const ready = doc.status === "ready";
  const failed = doc.status === "failed";

  return (
    <li className="lib-row">
      <div className="lib-main">
        {ready ? (
          <Link to={`/read/${doc.id}`} className="lib-title">
            {doc.title || doc.arxiv_id}
          </Link>
        ) : (
          <span className="lib-title lib-title-muted">{doc.title || doc.arxiv_id}</span>
        )}
        <div className="lib-meta">
          <span className={`status-pill status-${ready ? "ready" : failed ? "failed" : "pending"}`}>
            {ready ? "ready" : failed ? "failed" : doc.status}
          </span>
          <span className="lib-id">{doc.arxiv_id}</span>
          {doc.created_at && <span className="lib-time">{relativeTime(doc.created_at)}</span>}
        </div>
        {failed && doc.error && <p className="lib-error">{doc.error}</p>}
      </div>
      <div className="lib-actions">
        {failed && (
          <button type="button" className="lib-btn" onClick={onRetry}>
            Retry
          </button>
        )}
        {confirming ? (
          <>
            <button
              type="button"
              className="lib-btn lib-btn-danger"
              onClick={() => del.mutate()}
              disabled={del.isPending}
            >
              {del.isPending ? "Deleting…" : "Delete?"}
            </button>
            <button type="button" className="lib-btn" onClick={() => setConfirming(false)}>
              Cancel
            </button>
          </>
        ) : (
          <button
            type="button"
            className="lib-btn lib-btn-quiet"
            onClick={() => setConfirming(true)}
            aria-label="Delete paper"
          >
            Delete
          </button>
        )}
      </div>
    </li>
  );
}
