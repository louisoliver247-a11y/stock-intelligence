export async function request<T>(
  path: string,
  key: string,
  body?: unknown,
  method?: string,
): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method: method ?? (body === undefined ? "GET" : "POST"),
    credentials: "same-origin",
    headers: {
      "X-API-Key": key,
      ...(body === undefined ? {} : { "Content-Type": "application/json" }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : `Request failed (${response.status})`,
    );
  }
  return response.json() as Promise<T>;
}

export interface Status {
  services: { database: string; redis: string };
  market_session: string;
  feed: string;
  worker: string;
  integrity: string;
  latest_candle: string | null;
  timestamp: string;
  counts: Record<string, number>;
}
export interface Instrument {
  instrument_id: string;
  symbol: string;
  name: string;
  exchange: string;
}
export interface Candle {
  timestamp: string;
  open: string;
  high: string;
  low: string;
  close: string;
  volume: number;
  is_complete: boolean;
}
export interface Job {
  id: string;
  kind: string;
  state: string;
  created_at: string;
  error_code: string | null;
}

export interface ProviderStatus {
  provider: string;
  display_name: string;
  enabled: boolean;
  configured: boolean;
  preferred: boolean;
  authenticated: string;
  capabilities: Record<string, boolean>;
  websocket_status: string;
  instrument_mappings: number | null;
  last_successful_market_update: string | null;
}
