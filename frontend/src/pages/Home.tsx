import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";

export default function Home() {
  const [input, setInput] = useState("");
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const docs = useQuery({ queryKey: ["documents"], queryFn: api.listDocuments });

  const ingest = useMutation({
    mutationFn: api.ingest,
    onSuccess: (doc) => {
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      navigate(`/read/${doc.id}`);
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
        {docs.data && docs.data.length === 0 && (
          <p className="hint">Nothing here yet — open your first paper above.</p>
        )}
        <ul>
          {docs.data?.map((d) => (
            <li key={d.id}>
              {d.status === "ready" ? (
                <Link to={`/read/${d.id}`}>{d.title || d.arxiv_id}</Link>
              ) : (
                <span className="doc-failed">
                  {d.title || d.arxiv_id}
                  {d.error ? ` — ${d.error}` : ` — ${d.status}`}
                </span>
              )}
              <span className="doc-meta">{d.arxiv_id}</span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
