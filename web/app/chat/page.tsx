"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";

import { chat, ChatSource, getConversationMessages } from "@/lib/api";

type ChatMessage = {
  role: "user" | "assistant";
  text: string;
  sources?: ChatSource[];
  error?: boolean;
};

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [conversationId, setConversationId] = useState<string | undefined>(undefined);
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const stored = window.localStorage.getItem("intuition_conversation_id");
    if (!stored) return;
    setConversationId(stored);
    void (async () => {
      try {
        const out = await getConversationMessages(stored);
        const hydrated: ChatMessage[] = out.messages
          .filter((m) => m.role === "user" || m.role === "assistant")
          .map((m) => ({
            role: m.role as "user" | "assistant",
            text: m.content,
            sources: m.role === "assistant" ? m.sources ?? [] : undefined,
          }));
        setMessages(hydrated);
      } catch {
        // Ignore hydration failures; user can continue a fresh conversation.
      }
    })();
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const message = input.trim();
    if (!message || isSending) return;

    setError(null);
    setIsSending(true);
    setMessages((prev) => [...prev, { role: "user", text: message }]);
    setInput("");
    try {
      const out = await chat(message, conversationId);
      setConversationId(out.conversation_id);
      window.localStorage.setItem("intuition_conversation_id", out.conversation_id);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: out.answer_markdown, sources: out.sources ?? [] },
      ]);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Chat request failed";
      setError(msg);
      setMessages((prev) => [...prev, { role: "assistant", text: msg, error: true }]);
    } finally {
      setIsSending(false);
    }
  }

  return (
    <div className="min-h-screen p-6 md:p-10">
      <header className="flex items-center justify-between gap-4">
        <div className="flex items-baseline gap-3">
          <div className="text-2xl font-extrabold tracking-tight">Intuition</div>
          <div className="text-sm text-ink/70">Chat</div>
        </div>
        <nav className="flex items-center gap-2 text-sm">
          <Link className="border-2 border-ink px-3 py-1 shadow-[4px_4px_0_0_#111111] hover:bg-accent/40" href="/">
            Digest
          </Link>
          <Link className="border-2 border-ink bg-accent px-3 py-1 font-bold shadow-[4px_4px_0_0_#111111]" href="/chat">
            Chat
          </Link>
          <Link className="border-2 border-ink px-3 py-1 shadow-[4px_4px_0_0_#111111] hover:bg-accent/40" href="/browse">
            Browse
          </Link>
        </nav>
      </header>

      <main className="mt-8 grid gap-4">
        <section className="border-2 border-ink bg-paper p-6 shadow-[6px_6px_0_0_#111111]">
          <h1 className="text-3xl font-extrabold tracking-tight">Ask your bookmarks</h1>
          <p className="mt-2 text-sm text-ink/70">
            This will call <code className="font-mono">POST /api/chat</code> and show sources.
          </p>
        </section>

        <section className="border-2 border-ink bg-paper p-6 shadow-[4px_4px_0_0_#111111]">
          <div className="grid gap-4">
            {messages.length === 0 && (
              <div className="text-sm text-ink/70">
                Try: "What are the most useful dev setup tips in my bookmarks?"
              </div>
            )}
            {messages.map((m, idx) => (
              <div
                key={idx}
                className={`border-2 border-ink p-4 shadow-[4px_4px_0_0_#111111] ${
                  m.role === "user" ? "bg-accent/30" : "bg-paper"
                }`}
              >
                <div className="mb-2 text-xs font-bold uppercase tracking-wide">
                  {m.role === "user" ? "You" : "Assistant"}
                </div>
                <div className={`whitespace-pre-wrap text-sm ${m.error ? "font-bold" : ""}`}>
                  {m.text}
                </div>
                {!!m.sources?.length && (
                  <div className="mt-3 grid gap-2">
                    <div className="text-xs font-bold uppercase tracking-wide text-ink/70">Sources</div>
                    {m.sources.map((s, i) => (
                      <a
                        key={`${idx}-src-${i}`}
                        href={s.url ?? "#"}
                        target="_blank"
                        rel="noreferrer"
                        className="block border-2 border-ink bg-paper p-2 text-xs shadow-[3px_3px_0_0_#111111] hover:bg-accent/30"
                      >
                        <div className="font-bold">
                          {s.title || `Bookmark #${s.bookmark_id ?? "?"}`}
                        </div>
                        <div className="text-ink/70">
                          {s.author_name ?? "Unknown"} @{s.author_username ?? "unknown"}
                        </div>
                      </a>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>

          <form onSubmit={onSubmit} className="mt-5 flex flex-col gap-3 md:flex-row">
            <input
              className="w-full border-2 border-ink bg-paper px-3 py-2 text-sm shadow-[4px_4px_0_0_#111111] outline-none placeholder:text-ink/40"
              placeholder="Ask about your bookmarks…"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={isSending}
            />
            <button
              type="submit"
              disabled={isSending || !input.trim()}
              className="border-2 border-ink bg-accent px-4 py-2 text-sm font-bold shadow-[4px_4px_0_0_#111111] disabled:opacity-60 active:translate-x-[1px] active:translate-y-[1px] active:shadow-none"
            >
              {isSending ? "Thinking…" : "Send"}
            </button>
          </form>
          {error && (
            <div className="mt-3 border-2 border-ink bg-accent px-3 py-2 text-sm font-bold shadow-[4px_4px_0_0_#111111]">
              {error}
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

