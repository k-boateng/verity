export interface DocumentSummary {
  id: number;
  arxiv_id: string;
  title: string;
  authors: string;
  status: string;
  error: string;
  created_at: string | null;
}

export interface GraphNode {
  id: number;
  kind:
    | "section"
    | "equation"
    | "figure"
    | "table"
    | "citation"
    | "symbol"
    | "term"
    | "theorem"
    | "footnote";
  label: string;
  html_anchor: string;
  definition_anchor: string;
  excerpt: string;
  data: {
    excerpt_html?: string;
    section_label?: string;
    grounded?: boolean;
    source?: string;
    count?: number;
  };
}

export interface GraphEdge {
  source: number;
  target: number;
  kind: string;
}

export interface GraphResponse {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

async function handle<T>(resp: Response): Promise<T> {
  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const body = await resp.json();
      if (body.detail) detail = body.detail;
    } catch {
      /* not json */
    }
    throw new Error(detail);
  }
  return resp.json() as Promise<T>;
}

export const api = {
  listDocuments: () =>
    fetch("/api/documents").then((r) => handle<DocumentSummary[]>(r)),

  ingest: (arxivId: string) =>
    fetch("/api/documents", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ arxiv_id: arxivId }),
    }).then((r) => handle<DocumentSummary>(r)),

  getDocument: (docId: string | number) =>
    fetch(`/api/documents/${docId}`).then((r) => handle<DocumentSummary>(r)),

  getHtml: async (docId: string | number): Promise<string> => {
    const resp = await fetch(`/api/documents/${docId}/html`);
    if (!resp.ok) throw new Error(`document not ready (${resp.status})`);
    return resp.text();
  },

  getGraph: (docId: string | number) =>
    fetch(`/api/documents/${docId}/nodes`).then((r) => handle<GraphResponse>(r)),
};
