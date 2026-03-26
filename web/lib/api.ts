export type StatusResponse = {
  ok: boolean;
  db?: { path: string };
  bird?: { installed: boolean; available: boolean; path?: string; whoami?: any };
  imports?: { last_import_at?: string | null; last_import_result?: ImportResult | null };
};

export type ImportResult = {
  fetched: number;
  stored: number;
  skipped: number;
};

export type ImportResponse = {
  ok: boolean;
  result: ImportResult;
  enqueued_for_enrichment?: number;
};

export type DigestListItem = {
  id: number;
  period_start: string;
  period_end: string;
  created_at: string;
};

export type ListDigestsResponse = {
  ok: boolean;
  digests: DigestListItem[];
};

export type DigestDetailRaw = {
  id: number;
  period_start: string;
  period_end: string;
  created_at: string;
  content?: string;
  content_markdown?: string;
  data?: {
    themes?: Array<{
      theme_id?: string;
      title?: string;
      summary?: string;
      key_takeaways?: string[];
      bookmark_ids?: number[];
    }>;
  };
  citations?: ChatSource[];
};

export type GetDigestResponse = {
  ok: boolean;
  digest: DigestDetailRaw;
};

export type GenerateDigestResponse = {
  ok: boolean;
  digest: DigestDetailRaw;
};

export type ChatSource = {
  bookmark_id?: number;
  url?: string;
  title?: string | null;
  author_name?: string | null;
  author_username?: string | null;
  tweet_date?: string | null;
};

export type ChatResponse = {
  ok: boolean;
  conversation_id: string;
  answer_markdown: string;
  sources: ChatSource[];
};

export type ConversationMessage = {
  role: "user" | "assistant" | "system";
  content: string;
  sources?: ChatSource[];
  created_at?: string;
};

export type ConversationMessagesResponse = {
  ok: boolean;
  conversation_id: string;
  messages: ConversationMessage[];
};

export type SearchResult = {
  bookmark: {
    id: number;
    author_name: string;
    author_username: string;
    body: string;
    tweet_date: string;
    url: string;
    enrichment?: {
      tags?: Array<{ name: string; category?: string | null }>;
    } | null;
  };
  match?: { snippet?: string };
  score?: number;
};

export type SearchResponse = {
  ok: boolean;
  query: string;
  pagination?: { limit: number; offset: number };
  results: SearchResult[];
};

const API_BASE = "/api/proxy";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    cache: "no-store",
  });
  const raw = await res.text();
  let data: any = null;
  try {
    data = raw ? JSON.parse(raw) : null;
  } catch {
    data = null;
  }
  if (!res.ok) {
    const msg = data?.detail ?? data?.error?.message ?? (raw || "Request failed");
    throw new Error(msg);
  }
  return (data ?? ({} as T)) as T;
}

export function getStatus() {
  return request<StatusResponse>("/api/status");
}

export function importBookmarks(limit = 50) {
  return request<ImportResponse>("/api/import", {
    method: "POST",
    body: JSON.stringify({ limit, enqueue_enrichment: true }),
  });
}

export function runEnrichment(maxItems = 10) {
  return request("/api/enrich/run", { method: "POST", body: JSON.stringify({ max_items: maxItems }) });
}

export function search(q: string) {
  const params = new URLSearchParams({ q });
  return request<SearchResponse>(`/api/search?${params.toString()}`);
}

export function chat(message: string, conversationId?: string) {
  return request<ChatResponse>("/api/chat", {
    method: "POST",
    body: JSON.stringify({ message, conversation_id: conversationId }),
  });
}

export function getConversationMessages(conversationId: string) {
  return request<ConversationMessagesResponse>(`/api/conversations/${conversationId}/messages`);
}

export function generateDigest(periodStart?: string, periodEnd?: string) {
  return request<GenerateDigestResponse>("/api/digest/generate", {
    method: "POST",
    body: JSON.stringify({ period_start: periodStart ?? null, period_end: periodEnd ?? null }),
  });
}

export function listDigests() {
  return request<ListDigestsResponse>("/api/digests");
}

export function getDigest(id: number) {
  return request<GetDigestResponse>(`/api/digests/${id}`);
}

