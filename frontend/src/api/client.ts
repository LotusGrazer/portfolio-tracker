import type {
  Benchmark,
  Comparison,
  Holding,
  Summary,
  UploadResult,
} from "./types";

// Backend base URL. Override with VITE_API_URL at build/dev time if the Flask
// app runs elsewhere. CORS is enabled server-side, so direct calls work.
// Uses the IPv4 loopback (not "localhost") because Flask binds 127.0.0.1, while
// "localhost" can resolve to IPv6 ::1 first and fail to connect.
const BASE = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:5000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, init);
  } catch {
    throw new Error(
      `Could not reach the API at ${BASE}. Is the Flask backend running?`,
    );
  }
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const message =
      (body && (body as { error?: string }).error) ||
      `${res.status} ${res.statusText}`;
    throw new Error(message);
  }
  return body as T;
}

export interface BenchmarkInput {
  name: string;
  constituents: { ticker: string; weight_pct: number; exchange?: string }[];
}

export const api = {
  health: () => request<{ status: string }>("/health"),
  holdings: () => request<Holding[]>("/holdings"),
  summary: () => request<Summary>("/portfolio/summary"),
  benchmarks: () => request<Benchmark[]>("/benchmarks"),

  compare: (periods?: string[]) => {
    const qs = periods?.length ? `?periods=${periods.join(",")}` : "";
    return request<Comparison>(`/benchmarks/compare${qs}`);
  },

  uploadHoldings: (file: File, portfolio?: string, replace?: boolean) => {
    const form = new FormData();
    form.append("file", file);
    const params = new URLSearchParams();
    if (portfolio) params.set("portfolio", portfolio);
    if (replace) params.set("replace", "true");
    const qs = params.toString();
    return request<UploadResult>(`/holdings/upload${qs ? `?${qs}` : ""}`, {
      method: "POST",
      body: form,
    });
  },

  createBenchmark: (payload: BenchmarkInput) =>
    request<Benchmark>("/benchmarks/create", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
};
