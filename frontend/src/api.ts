export interface DocumentSummary {
  id: number;
  arxiv_id: string;
  source: "arxiv" | "pdf";
  filename: string;
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

// Empty in dev (Vite proxies /api to the backend); in production set
// VITE_API_BASE to the deployed backend URL for cross-origin calls.
const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

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
    fetch(API_BASE + "/api/documents").then((r) => handle<DocumentSummary[]>(r)),

  ingest: (arxivId: string) =>
    fetch(API_BASE + "/api/documents", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ arxiv_id: arxivId }),
    }).then((r) => handle<DocumentSummary>(r)),

  uploadPdf: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return fetch(API_BASE + "/api/documents/pdf", { method: "POST", body: form }).then((r) =>
      handle<DocumentSummary>(r),
    );
  },

  getDocument: (docId: string | number) =>
    fetch(`${API_BASE}/api/documents/${docId}`).then((r) => handle<DocumentSummary>(r)),

  deleteDocument: (docId: number) =>
    fetch(`${API_BASE}/api/documents/${docId}`, { method: "DELETE" }).then((r) =>
      handle<{ deleted: number }>(r),
    ),

  checkpoint: (
    docId: string | number,
    body: { section_anchor: string; section_label?: string; answer?: string },
  ) =>
    fetch(`${API_BASE}/api/documents/${docId}/checkpoint`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then((r) => handle<CheckpointResult>(r)),

  getHtml: async (docId: string | number): Promise<string> => {
    const resp = await fetch(`${API_BASE}/api/documents/${docId}/html`);
    if (!resp.ok) throw new Error(`document not ready (${resp.status})`);
    return resp.text();
  },

  getGraph: (docId: string | number) =>
    fetch(`${API_BASE}/api/documents/${docId}/nodes`).then((r) => handle<GraphResponse>(r)),

  getConfig: () => fetch(API_BASE + "/api/config").then((r) => handle<{ llm_configured: boolean }>(r)),

  explainEquation: (docId: string | number, req: { latex: string; context?: string; symbols?: string[] }) =>
    fetch(`${API_BASE}/api/documents/${docId}/explain-equation`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    }).then((r) => handle<{ mode: ResolveMode; content: string }>(r)),

  defineSymbol: (docId: string | number, nodeId: number) =>
    fetch(`${API_BASE}/api/documents/${docId}/nodes/${nodeId}/define`, { method: "POST" }).then((r) =>
      handle<{ id: number; excerpt: string; data: GraphNode["data"] }>(r),
    ),

  resolve: (docId: string | number, req: ResolveRequest) =>
    fetch(`${API_BASE}/api/documents/${docId}/resolve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    }).then((r) => handle<ResolveResult>(r)),

  listChats: (docId: string | number) =>
    fetch(`${API_BASE}/api/documents/${docId}/chats`).then((r) => handle<ChatSummary[]>(r)),

  openChat: (docId: string | number, seed: ChatCreateRequest) =>
    fetch(`${API_BASE}/api/documents/${docId}/chats`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(seed),
    }).then((r) => handle<Chat>(r)),

  getChat: (chatId: number) =>
    fetch(`${API_BASE}/api/chats/${chatId}`).then((r) => handle<Chat>(r)),

  sendChatMessage: async function* (
    chatId: number,
    content: string,
    signal?: AbortSignal,
  ): AsyncGenerator<string> {
    const resp = await fetch(`${API_BASE}/api/chats/${chatId}/message`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content }),
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

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface ChatCreateRequest {
  selection: string;
  section_label?: string;
  section_anchor?: string;
  paragraph?: string;
  dependencies?: string[];
}

export interface ChatSummary {
  id: number;
  selection: string;
  section_label: string;
  section_anchor: string;
  question_count: number;
  updated_at: string | null;
}

export interface Chat {
  id: number;
  document_id: number;
  selection: string;
  section_label: string;
  section_anchor: string;
  paragraph: string;
  dependencies: string[];
  messages: ChatMessage[];
}

export interface ResolveRequest {
  selection: string;
  paragraph?: string;
  section?: string;
  dependencies?: string[];
}

export type ResolveMode =
  | "retrieved"
  | "generated"
  | "abstained"
  | "unconfigured"
  | "error";

export interface ResolveResult {
  mode: ResolveMode;
  content: string;
  label: string;
  anchor: string;
  section_label?: string;
  model?: string;
}

export interface CheckpointPoint {
  point: string;
  status: "hit" | "partial" | "miss";
}

export interface CheckpointResult {
  key_points: CheckpointPoint[];
  feedback: string;
  error?: boolean;
}

