import { useEffect, useState } from "react";
export type Json = Record<string, unknown>;
export type Manifest = {
  schema: string;
  version: string;
  platform: string;
  source_revision: string;
  filename: string;
  size: number;
  sha256: string;
  components: string[];
  model_included: boolean;
  signature: string;
  license: string;
  source_archive: {
    filename: string;
    size: number;
    sha256: string;
    source_revision: string;
  };
  distribution_clearance: { status: string; reference: string };
  notes: string;
  minimum_os: string;
};
export type Release = {
  id: string;
  manifest: Manifest;
  state: { status: string; channel: string; reason: string };
  created_at: number;
  event_id: string;
  revision: number;
  download_requests: number;
};
export type Session = {
  user: { id: string; client_id: string; name: string; role: string };
  csrf: string;
  expires_at: number;
};
export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
  ) {
    super(code);
  }
}
export async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const r = await fetch("/portal-api/" + path, {
    credentials: "same-origin",
    ...options,
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...options.headers,
    },
  });
  const data = await r.json();
  if (!r.ok) throw new ApiError(r.status, data.detail || "REQUEST_FAILED");
  return data as T;
}
export function useData<T>(path: string, revision = 0) {
  const [data, setData] = useState<T>();
  const [error, setError] = useState<Error>();
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    const a = new AbortController();
    setData(undefined);
    setError(undefined);
    setLoading(true);
    request<T>(path, { signal: a.signal })
      .then((value) => {
        if (!a.signal.aborted) setData(value);
      })
      .catch((e) => {
        if (!a.signal.aborted) setError(e);
      })
      .finally(() => {
        if (!a.signal.aborted) setLoading(false);
      });
    return () => a.abort();
  }, [path, revision]);
  return { data, error, loading };
}
export const object = (v: unknown): Json =>
  v !== null && typeof v === "object" && !Array.isArray(v) ? (v as Json) : {};
export const rows = (v: unknown): Json[] =>
  Array.isArray(v) ? v.map(object) : [];
export const text = (v: unknown) =>
  v === undefined || v === null ? "—" : String(v);
export const date = (v: unknown) =>
  v
    ? new Date(typeof v === "number" ? v * 1000 : String(v)).toLocaleString(
        "ko-KR",
      )
    : "—";
export const number = (v: unknown) =>
  typeof v === "number" ? v.toLocaleString("ko-KR") : "—";
export const size = (bytes: number) => `${(bytes / 1048576).toFixed(1)} MB`;
