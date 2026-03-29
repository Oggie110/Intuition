"use client";

import dynamic from "next/dynamic";

const DigestHome = dynamic(() => import("./home-client"), {
  ssr: false,
  loading: () => (
    <div className="min-h-screen bg-paper p-6 md:p-10 text-ink">
      <p className="text-sm font-bold text-ink/70">Loading…</p>
    </div>
  ),
});

export default function DigestHomeEntry() {
  return <DigestHome />;
}
