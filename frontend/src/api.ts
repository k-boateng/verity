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
    sections?: string[];
    label_mathml?: string;
    macro_name?: string;
    definition_status?: "unresolved" | "grounded" | "inferred" | "undefined";
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

  getConfig: () => fetch("/api/config").then((r) => handle<{ llm_configured: boolean }>(r)),

  resolve: (docId: string | number, req: ResolveRequest) =>
    fetch(`/api/documents/${docId}/resolve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    }).then((r) => handle<ResolveResult>(r)),

  chatStream: async function* (
    docId: string | number,
    req: ChatRequest,
    signal?: AbortSignal,
  ): AsyncGenerator<string> {
    const resp = await fetch(`/api/documents/${docId}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
      signal,
    });
    if (!resp.ok || !resp.body) throw new Error(`chat failed (${resp.status})`);
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      yield decoder.decode(value, { stream: true });
    }
  },
};

export interface ResolveRequest {
  selection: string;
  paragraph?: string;
  section?: string;
  dependencies?: string[];
}

export type ResolveMode = "retrieved" | "generated" | "abstained" | "unconfigured";

export interface ResolveResult {
  mode: ResolveMode;
  content: string;
  label: string;
  anchor: string;
  section_label?: string;
  model?: string;
}

export interface ChatRequest {
  messages: { role: "user" | "assistant"; content: string }[];
  paragraph?: string;
  selection?: string;
  section?: string;
  dependencies?: string[];
}
