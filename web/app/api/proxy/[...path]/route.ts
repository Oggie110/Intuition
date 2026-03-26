import { NextRequest, NextResponse } from "next/server";

const BACKEND_BASE =
  process.env.BACKEND_API_BASE ??
  process.env.NEXT_PUBLIC_API_BASE ??
  "http://127.0.0.1:8010";

async function forward(req: NextRequest, method: string, path: string[]) {
  const target = new URL(`${BACKEND_BASE}/${path.join("/")}`);
  req.nextUrl.searchParams.forEach((value, key) => {
    target.searchParams.set(key, value);
  });

  const headers = new Headers(req.headers);
  headers.delete("host");

  const init: RequestInit = {
    method,
    headers,
    body: method === "GET" || method === "HEAD" ? undefined : await req.text(),
    redirect: "follow",
  };

  const upstream = await fetch(target, init);
  const responseHeaders = new Headers(upstream.headers);
  responseHeaders.delete("content-encoding");
  responseHeaders.delete("content-length");

  return new NextResponse(await upstream.text(), {
    status: upstream.status,
    headers: responseHeaders,
  });
}

export async function GET(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  return forward(req, "GET", path);
}

export async function POST(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  return forward(req, "POST", path);
}

export async function PUT(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  return forward(req, "PUT", path);
}

export async function PATCH(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  return forward(req, "PATCH", path);
}

export async function DELETE(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  return forward(req, "DELETE", path);
}

