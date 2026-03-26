 "use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import {
  DigestDetailRaw,
  DigestListItem,
  generateDigest,
  getDigest,
  getStatus,
  importBookmarks,
  listDigests,
  StatusResponse,
} from "@/lib/api";

type ThemeCluster = {
  theme_id: string;
  title: string;
  summary: string;
  key_takeaways: string[];
  bookmark_ids: number[];
};

type DigestDetail = {
  id: number;
  periodStart: string;
  periodEnd: string;
  createdAt: string;
  markdown: string;
  themes: ThemeCluster[];
  citations: Array<{ bookmark_id?: number; url?: string }>;
};

function normalizeDigest(raw: DigestDetailRaw): DigestDetail {
  const themesRaw = raw.data?.themes ?? [];
  const themes: ThemeCluster[] = themesRaw.map((t, i) => ({
    theme_id: t.theme_id ?? `theme-${i + 1}`,
    title: t.title ?? "Untitled theme",
    summary: t.summary ?? "",
    key_takeaways: t.key_takeaways ?? [],
    bookmark_ids: t.bookmark_ids ?? [],
  }));
  return {
    id: raw.id,
    periodStart: raw.period_start,
    periodEnd: raw.period_end,
    createdAt: raw.created_at,
    markdown: raw.content_markdown ?? raw.content ?? "",
    themes,
    citations: raw.citations ?? [],
  };
}

export default function Home() {
  const [mounted, setMounted] = useState(false);
  const [busy, setBusy] = useState<"refresh" | "fetch" | "digest" | "pick" | null>(null);
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [digests, setDigests] = useState<DigestListItem[]>([]);
  const [selectedDigestId, setSelectedDigestId] = useState<number | null>(null);
  const [activeDigest, setActiveDigest] = useState<DigestDetail | null>(null);

  const importResult = status?.imports?.last_import_result;

  const digestMeta = useMemo(() => {
    if (!activeDigest) return null;
    return `${activeDigest.periodStart} to ${activeDigest.periodEnd}`;
  }, [activeDigest]);

  const renderedDigestMarkdown = useMemo(() => {
    const md = activeDigest?.markdown ?? "";
    if (!md) return md;
    const map = new Map<number, string>();
    for (const c of activeDigest?.citations ?? []) {
      if (typeof c.bookmark_id === "number" && c.url) {
        map.set(c.bookmark_id, c.url);
      }
    }
    return md.replace(/\[@bm:(\d+)\]/g, (full, idRaw) => {
      const id = Number(idRaw);
      const url = map.get(id);
      if (!url) return full;
      return `[@bm:${id}](${url})`;
    });
  }, [activeDigest]);

  async function refresh() {
    const s = await getStatus();
    setStatus(s);
  }

  async function loadDigestById(id: number) {
    setBusy("pick");
    setError(null);
    try {
      const data = await getDigest(id);
      setActiveDigest(normalizeDigest(data.digest));
      setSelectedDigestId(id);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load digest");
    } finally {
      setBusy(null);
    }
  }

  async function initialLoad() {
    setBusy("refresh");
    setError(null);
    try {
      const [s, d] = await Promise.all([getStatus(), listDigests()]);
      setStatus(s);
      setDigests(d.digests ?? []);
      if (d.digests?.length) {
        await loadDigestById(d.digests[0].id);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setBusy(null);
    }
  }

  async function onFetch() {
    setError(null);
    setBusy("fetch");
    try {
      await importBookmarks(50);
      await refresh();
    } catch (e: any) {
      setError(e?.message ?? "Failed to import");
    } finally {
      setBusy(null);
    }
  }

  async function onDigest() {
    setError(null);
    setBusy("digest");
    try {
      const out = await generateDigest();
      const nextDigest = normalizeDigest(out.digest);
      setActiveDigest(nextDigest);
      setSelectedDigestId(nextDigest.id);
      setDigests((prev) => {
        const exists = prev.some((d) => d.id === nextDigest.id);
        const item: DigestListItem = {
          id: nextDigest.id,
          period_start: nextDigest.periodStart,
          period_end: nextDigest.periodEnd,
          created_at: nextDigest.createdAt,
        };
        return exists ? prev : [item, ...prev];
      });
      await refresh();
    } catch (e: any) {
      setError(e?.message ?? "Failed to generate digest");
    } finally {
      setBusy(null);
    }
  }

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    void initialLoad();
  }, []);

  return (
    <div className="min-h-screen p-6 md:p-10">
      <header className="flex items-center justify-between gap-4">
        <div className="flex items-baseline gap-3">
          <div className="text-2xl font-extrabold tracking-tight">Intuition</div>
          <div className="text-sm text-ink/70">Bookmark Intelligence</div>
        </div>
        <nav className="flex items-center gap-2 text-sm">
          <Link
            className="border-2 border-ink px-3 py-1 shadow-[4px_4px_0_0_#111111] hover:bg-accent/40"
            href="/"
          >
            Digest
          </Link>
          <Link
            className="border-2 border-ink px-3 py-1 shadow-[4px_4px_0_0_#111111] hover:bg-accent/40"
            href="/chat"
          >
            Chat
          </Link>
          <Link
            className="border-2 border-ink px-3 py-1 shadow-[4px_4px_0_0_#111111] hover:bg-accent/40"
            href="/browse"
          >
            Browse
          </Link>
        </nav>
      </header>

      <main className="mt-8 grid gap-6">
        <section className="border-2 border-ink bg-paper p-6 shadow-[6px_6px_0_0_#111111]">
          <div className="flex items-start justify-between gap-6">
            <div>
              <h1 className="text-3xl font-extrabold tracking-tight">Weekly digest</h1>
              <p className="mt-2 text-sm text-ink/70">
                Fetch bookmarks, enrich them, and generate a themed summary.
              </p>
              <div className="mt-4 flex flex-wrap gap-3 text-xs text-ink/70">
                <button
                  className="border-2 border-ink bg-paper px-3 py-1 font-bold shadow-[3px_3px_0_0_#111111] hover:bg-accent/40"
                  onClick={() => refresh()}
                  disabled={busy !== null}
                >
                  Refresh status
                </button>
                {status?.bird && (
                  <div className="border-2 border-ink px-2 py-1 shadow-[3px_3px_0_0_#111111]">
                    Bird:{" "}
                    <span className="font-bold">
                      {status.bird.available ? "available" : status.bird.installed ? "installed" : "missing"}
                    </span>
                  </div>
                )}
                {status?.imports?.last_import_at && (
                  <div className="border-2 border-ink px-2 py-1 shadow-[3px_3px_0_0_#111111]">
                    Last import: <span className="font-bold">{new Date(status.imports.last_import_at).toLocaleString()}</span>
                  </div>
                )}
                {importResult && (
                  <div className="border-2 border-ink px-2 py-1 shadow-[3px_3px_0_0_#111111]">
                    Import:{" "}
                    <span className="font-bold">
                      fetched {importResult.fetched}, stored {importResult.stored}, skipped {importResult.skipped}
                    </span>
                  </div>
                )}
              </div>
              {error && (
                <div className="mt-4 border-2 border-ink bg-accent px-3 py-2 text-sm font-bold shadow-[4px_4px_0_0_#111111]">
                  {error}
                </div>
              )}
            </div>
            <div className="flex gap-2">
              <button
                className="border-2 border-ink bg-accent px-4 py-2 text-sm font-bold shadow-[4px_4px_0_0_#111111] disabled:opacity-60 active:translate-x-[1px] active:translate-y-[1px] active:shadow-none"
                onClick={onFetch}
                disabled={busy !== null}
              >
                {busy === "fetch" ? "Fetching…" : "Fetch bookmarks"}
              </button>
              <button
                className="border-2 border-ink bg-paper px-4 py-2 text-sm font-bold shadow-[4px_4px_0_0_#111111] disabled:opacity-60 hover:bg-accent/40 active:translate-x-[1px] active:translate-y-[1px] active:shadow-none"
                onClick={onDigest}
                disabled={busy !== null}
              >
                {busy === "digest" ? "Generating…" : "Generate digest"}
              </button>
            </div>
          </div>
        </section>

        <section className="border-2 border-ink bg-paper p-5 shadow-[4px_4px_0_0_#111111]">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-lg font-extrabold">
                {activeDigest ? `Digest #${activeDigest.id}` : "No digest yet"}
              </div>
              {digestMeta && <div className="text-sm text-ink/70">{digestMeta}</div>}
            </div>
            {mounted ? (
              <div className="relative">
                <select
                  className="appearance-none border-2 border-ink bg-paper px-3 py-2 pr-10 text-sm font-bold shadow-[4px_4px_0_0_#111111] outline-none disabled:opacity-60"
                  value={selectedDigestId ?? ""}
                  disabled={!digests.length || busy !== null}
                  onChange={(e) => {
                    const next = Number(e.target.value);
                    if (next) void loadDigestById(next);
                  }}
                >
                  <option value="">Select digest</option>
                  {digests.map((d) => (
                    <option key={d.id} value={d.id}>
                      #{d.id} ({d.period_start} to {d.period_end})
                    </option>
                  ))}
                </select>
                <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-ink">
                  ▾
                </span>
              </div>
            ) : (
              <div className="h-[42px] w-[280px] border-2 border-ink bg-paper shadow-[4px_4px_0_0_#111111]" />
            )}
          </div>
        </section>

        <section className="grid gap-4 md:grid-cols-2">
          {(activeDigest?.themes?.length ? activeDigest.themes : []).slice(0, 6).map((theme) => (
            <div
              key={theme.theme_id}
              className="border-2 border-ink bg-paper p-5 shadow-[4px_4px_0_0_#111111]"
            >
              <div className="flex items-center justify-between">
                <div className="text-lg font-extrabold">{theme.title}</div>
                <div className="border-2 border-ink bg-accent px-2 py-0.5 text-xs font-bold">
                  {theme.bookmark_ids.length}
                </div>
              </div>
              <p className="mt-3 text-sm text-ink/80">
                {theme.summary || "No summary for this cluster."}
              </p>
              {theme.key_takeaways.length > 0 && (
                <ul className="mt-3 list-disc pl-4 text-xs text-ink/70">
                  {theme.key_takeaways.slice(0, 3).map((k, i) => (
                    <li key={`${theme.theme_id}-${i}`}>{k}</li>
                  ))}
                </ul>
              )}
            </div>
          ))}
          {!activeDigest?.themes?.length && (
            <div className="border-2 border-ink bg-paper p-5 shadow-[4px_4px_0_0_#111111] md:col-span-2">
              <div className="text-sm text-ink/70">No theme clusters yet. Generate a digest to populate this section.</div>
            </div>
          )}
        </section>

        <section className="border-2 border-ink bg-paper p-5 shadow-[4px_4px_0_0_#111111]">
          <div className="text-lg font-extrabold">Digest markdown</div>
          <article className="mt-3 text-sm leading-7 text-ink/90">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                h1: ({ children }) => <h1 className="mb-3 text-2xl font-extrabold">{children}</h1>,
                h2: ({ children }) => <h2 className="mb-2 mt-5 text-xl font-extrabold">{children}</h2>,
                h3: ({ children }) => <h3 className="mb-2 mt-4 text-lg font-bold">{children}</h3>,
                p: ({ children }) => <p className="mb-3">{children}</p>,
                ul: ({ children }) => <ul className="mb-3 list-disc pl-5">{children}</ul>,
                ol: ({ children }) => <ol className="mb-3 list-decimal pl-5">{children}</ol>,
                li: ({ children }) => <li className="mb-1">{children}</li>,
                a: ({ href, children }) => (
                  <a
                    href={href}
                    target="_blank"
                    rel="noreferrer"
                    className="font-bold underline decoration-2 underline-offset-2 hover:bg-accent/40"
                  >
                    {children}
                  </a>
                ),
                hr: () => <hr className="my-4 border-ink/30" />,
              }}
            >
              {renderedDigestMarkdown || "No digest markdown yet."}
            </ReactMarkdown>
          </article>
        </section>
      </main>
    </div>
  );
}
