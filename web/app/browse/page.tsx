"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";

import { SearchResult, search } from "@/lib/api";

export default function BrowsePage() {
  const [query, setQuery] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSearch(e: FormEvent) {
    e.preventDefault();
    const q = query.trim();
    if (!q) {
      setResults([]);
      setSubmittedQuery("");
      return;
    }
    setIsLoading(true);
    setError(null);
    setSubmittedQuery(q);
    try {
      const out = await search(q);
      setResults(out.results ?? []);
    } catch (err: unknown) {
      setResults([]);
      setError(err instanceof Error ? err.message : "Search failed");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="min-h-screen p-6 md:p-10">
      <header className="flex items-center justify-between gap-4">
        <div className="flex items-baseline gap-3">
          <div className="text-2xl font-extrabold tracking-tight">Intuition</div>
          <div className="text-sm text-ink/70">Browse</div>
        </div>
        <nav className="flex items-center gap-2 text-sm">
          <Link className="border-2 border-ink px-3 py-1 shadow-[4px_4px_0_0_#111111] hover:bg-accent/40" href="/">
            Digest
          </Link>
          <Link className="border-2 border-ink px-3 py-1 shadow-[4px_4px_0_0_#111111] hover:bg-accent/40" href="/chat">
            Chat
          </Link>
          <Link className="border-2 border-ink bg-accent px-3 py-1 font-bold shadow-[4px_4px_0_0_#111111]" href="/browse">
            Browse
          </Link>
        </nav>
      </header>

      <main className="mt-8 grid gap-4">
        <section className="border-2 border-ink bg-paper p-6 shadow-[6px_6px_0_0_#111111]">
          <h1 className="text-3xl font-extrabold tracking-tight">Browse & search</h1>
          <p className="mt-2 text-sm text-ink/70">
            This will call <code className="font-mono">GET /api/search</code> with filters.
          </p>
        </section>

        <section className="border-2 border-ink bg-paper p-6 shadow-[4px_4px_0_0_#111111]">
          <form onSubmit={onSearch} className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <input
              className="w-full border-2 border-ink bg-paper px-3 py-2 text-sm shadow-[4px_4px_0_0_#111111] outline-none placeholder:text-ink/40"
              placeholder="Search bookmarks (FTS5)…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <button
              type="submit"
              disabled={isLoading || !query.trim()}
              className="border-2 border-ink bg-accent px-4 py-2 text-sm font-bold shadow-[4px_4px_0_0_#111111] disabled:opacity-60 active:translate-x-[1px] active:translate-y-[1px] active:shadow-none"
            >
              {isLoading ? "Searching…" : "Search"}
            </button>
          </form>

          {error && (
            <div className="mt-4 border-2 border-ink bg-accent px-3 py-2 text-sm font-bold shadow-[4px_4px_0_0_#111111]">
              {error}
            </div>
          )}

          <div className="mt-6 text-sm text-ink/70">
            {submittedQuery ? `Results for "${submittedQuery}"` : "Run a search to browse bookmarks."}
          </div>

          <div className="mt-4 grid gap-3">
            {results.map((r) => (
              <article
                key={r.bookmark.id}
                className="border-2 border-ink bg-paper p-4 shadow-[4px_4px_0_0_#111111]"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="font-bold">
                    {r.bookmark.author_name} @{r.bookmark.author_username}
                  </div>
                  <div className="text-xs text-ink/70">
                    {r.bookmark.tweet_date} {typeof r.score === "number" ? `· score ${r.score.toFixed(2)}` : ""}
                  </div>
                </div>

                <p
                  className="mt-2 text-sm text-ink/90"
                  dangerouslySetInnerHTML={{
                    __html:
                      r.match?.snippet ||
                      r.bookmark.body.slice(0, 220) + (r.bookmark.body.length > 220 ? "…" : ""),
                  }}
                />

                <div className="mt-3 flex flex-wrap items-center gap-2">
                  {(r.bookmark.enrichment?.tags ?? []).slice(0, 6).map((t, i) => (
                    <span
                      key={`${r.bookmark.id}-tag-${i}`}
                      className="border-2 border-ink bg-accent/40 px-2 py-0.5 text-xs font-bold"
                    >
                      {t.name}
                    </span>
                  ))}
                </div>

                <div className="mt-3">
                  <a
                    className="border-2 border-ink bg-paper px-2 py-1 text-xs font-bold shadow-[3px_3px_0_0_#111111] hover:bg-accent/40"
                    href={r.bookmark.url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Open tweet
                  </a>
                </div>
              </article>
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}

