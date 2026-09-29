import { useCallback, useEffect, useState } from "react";
import {
  request,
  type Candle,
  type Instrument,
  type Job,
  type Status,
  type ProviderStatus,
} from "./api";
import { Users } from "./Users";
import { LoginPage } from "./LoginPage";
import { Chart } from "./Chart";

const later = [
  "Scanner",
  "Stock Analysis",
  "Strategies",
  "Backtests",
  "Portfolio",
  "Trade Journal",
  "Alerts",
];
const human = (value: string) => value.toLowerCase().replaceAll("_", " ");

export default function App() {
  const [token, setToken] = useState("");
  const [loginNotice, setLoginNotice] = useState("");
  useEffect(() => {
    const expired = (event: Event) => {
      if (token && (event as CustomEvent<string>).detail === token) {
        setToken("");
        setLoginNotice("Your session has expired. Please sign in again.");
      }
    };
    window.addEventListener("session-expired", expired);
    return () => window.removeEventListener("session-expired", expired);
  }, [token]);
  if (!token) return <LoginPage notice={loginNotice} onLogin={value => {
    setLoginNotice(""); setToken(value);
  }} />;
  return <Workspace apiKey={token} onSignOut={() => setToken("")} />;
}

function Workspace({ apiKey: key, onSignOut }: { apiKey: string; onSignOut: () => void }) {
  const [page, setPage] = useState("Dashboard");
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [providers, setProviders] = useState<ProviderStatus[]>([]);
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [activeOnly, setActiveOnly] = useState(true);
  const [selectedProvider, setSelectedProvider] = useState("");
  const [instruments, setInstruments] = useState<Instrument[]>([]);
  const [instrument, setInstrument] = useState("");
  const [jobs, setJobs] = useState<Job[]>([]);
  const [candles, setCandles] = useState<Candle[]>([]);
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [calendar, setCalendar] = useState("");
  const [theme, setTheme] = useState("dark");
  const refresh = useCallback(async () => {
    if (!key) return;
    try {
      setStatus(await request<Status>("/market/status", key));
      const [providerList, recent] = await Promise.all([
        request<ProviderStatus[]>("/providers", key),
        request<Job[]>("/jobs", key),
      ]);
      setProviders(providerList);
      setJobs(recent);
      setError("");
    } catch (e) {
      setError((e as Error).message);
    }
  }, [key]);
  useEffect(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), 15000);
    return () => clearInterval(timer);
  }, [refresh]);
  useEffect(() => {
    if (!key) return;
    let cancelled = false;
    const timer = setTimeout(() => {
      const query = new URLSearchParams({q: search, offset: String(offset), limit: "50"});
      if (activeOnly) query.set("active", "true");
      else query.set("active", "false");
      request<Instrument[]>(`/instruments?${query}`, key).then(list => {
        if (!cancelled) setInstruments(list);
      }).catch(e => { if (!cancelled) setError(e.message); });
    }, 250);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [key, search, offset, activeOnly]);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  async function action(work: () => Promise<void>, refreshAfter = true) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await work();
      if (refreshAfter) await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const queueHistory = () =>
    action(async () => {
      const result = await request<{ job_id: string }>("/history/ingest", key, {
        instrument_id: instrument,
        provider: selectedProvider || null,
        timeframe: "1m",
        start,
        end,
      });
      setNotice(`History queued · ${result.job_id}`);
    });
  const loadChart = () =>
    action(async () => {
      const params = new URLSearchParams({
        instrument_id: instrument,
        start: `${start}T00:00:00+05:30`,
        end: `${end}T23:59:59+05:30`,
        timeframe: "1m",
      });
      const data = await request<Candle[]>(`/candles?${params}`, key);
      setCandles(data.filter((c) => c.is_complete));
      setNotice(
        `${data.filter((c) => c.is_complete).length} complete candles loaded; partial candles excluded. Maximum 5,000 rows per request.`,
      );
    });

  return (
    <div className="terminal">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">SI</span>
          <div>
            STOCK INTELLIGENCE<small>INDIAN EQUITIES / RESEARCH</small>
          </div>
        </div>
        <p className="nav-label">WORKSPACE</p>
        <nav aria-label="Primary navigation">
          {[
            "Dashboard",
            "Scanner",
            "Charts",
            "Stock Analysis",
            "Strategies",
            "Backtests",
            "Portfolio",
            "Trade Journal",
            "Alerts",
            "Settings",
            "Users",
          ].map((name) => (
            <button
              key={name}
              className={page === name ? "nav-item selected" : "nav-item"}
              onClick={() => setPage(name)}
            >
              <span>{name}</span>
              {later.includes(name) && <span className="soon">LATER</span>}
            </button>
          ))}
        </nav>
        <div className="sidebar-footer">
          <span className="dot amber" /> Foundation build{" "}
          <small>Milestones 0–1 · Data infrastructure</small>
        </div>
      </aside>
      <main>
        <header>
          <div className="breadcrumb">
            Workspace <span>/</span> {page}
          </div>
          <div className="header-actions">
            <button disabled={busy} onClick={async () => {
              setBusy(true);
              try { await request("/auth/logout", key, {}); }
              catch { /* Clear this browser's session even if the server is unavailable. */ }
              finally { onSignOut(); }
            }}>Sign out</button>
            <span className="tag">NSE · IST</span>
            <button
              onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
              aria-label="Toggle color theme"
            >
              {theme === "dark" ? "Light" : "Dark"}
            </button>
          </div>
        </header>
        <div className="content">
          <div className="page-heading">
            <div>
              <p className="eyebrow">MARKET DATA OPERATIONS</p>
              <h1>
                {page === "Dashboard" ? "A clear view of your data." : page}
              </h1>
              <p className="muted">
                Verified inputs are the foundation of explainable analysis.
              </p>
            </div>
            <button disabled={!key || busy} onClick={() => void refresh()}>
              ↻ Refresh
            </button>
          </div>
          {error && (
            <div role="alert" className="message error">
              {error} · Check backend connectivity and configuration.
            </div>
          )}
          {notice && (
            <div role="status" className="message">
              {notice}
            </div>
          )}
          {page === "Users" ? <Users apiKey={key} /> : later.includes(page) ? (
            <section className="panel empty">
              <h2>{page} is scheduled for a later milestone</h2>
              <p>
                Market-data integrity must be verified before analytical
                features are enabled.
              </p>
              <button onClick={() => setPage("Dashboard")}>
                Return to data operations
              </button>
            </section>
          ) : (
            <>
              <div className="metrics">
                {[
                  [
                    "Exchange session",
                    status?.market_session ?? "UNKNOWN",
                    "Explicit session calendar",
                  ],
                  [
                    "Stored candles",
                    status?.counts.candles?.toLocaleString() ?? "—",
                    "Canonical historical data",
                  ],
                  [
                    "Instruments",
                    status?.counts.instruments?.toLocaleString() ?? "—",
                    "Synchronized instrument master",
                  ],
                  [
                    "Quality issues",
                    status?.counts.quality_issues?.toLocaleString() ?? "—",
                    "Unresolved integrity checks",
                  ],
                ].map(([label, value, hint]) => (
                  <section className="panel metric" key={label}>
                    <p>{label}</p>
                    <strong>{value}</strong>
                    <small>{hint}</small>
                  </section>
                ))}
              </div>
              <div className="integrity-strip">
                <span className="dot amber" />
                <strong>Integrity gate: not verified</strong>
                <span>
                  Live provider comparison and calendar validation are required
                  before analysis.
                </span>
              </div>
              <div className="workspace-grid">
                <section className="panel chart-panel">
                  <div className="panel-heading">
                    <div>
                      <h2>Price history</h2>
                      <p className="muted">
                        Completed 1-minute candles · NSE · Asia/Kolkata
                      </p>
                    </div>
                    <span className="tag">FACT / OHLCV</span>
                  </div>
                  <div className="data-controls">
                    <label>Search instruments
                      <input value={search} placeholder="Symbol, name or ISIN" onChange={e => {
                        setSearch(e.target.value); setOffset(0); setInstrument(""); setCandles([]);
                      }} />
                    </label>
                    <label>Status
                      <select value={String(activeOnly)} onChange={e => {
                        setActiveOnly(e.target.value === "true"); setOffset(0); setInstrument(""); setCandles([]);
                      }}><option value="true">Active</option><option value="false">Inactive</option></select>
                    </label>
                    <button disabled={offset === 0} onClick={() => { setOffset(Math.max(0, offset - 50)); setInstrument(""); setCandles([]); }}>Previous instruments</button>
                    <button disabled={instruments.length < 50} onClick={() => { setOffset(offset + 50); setInstrument(""); setCandles([]); }}>Next instruments</button>
                    <span>Page {offset / 50 + 1}</span>
                  </div>
                  <div className="data-controls">
                    <label>
                      Instrument
                      <select
                        value={instrument}
                        onChange={(e) => {
                          setInstrument(e.target.value);
                          setCandles([]);
                        }}
                      >
                        <option value="">Select instrument</option>
                        {instruments.map((i) => (
                          <option key={i.instrument_id} value={i.instrument_id}>
                            {i.symbol} · {i.exchange}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      From
                      <input
                        type="date"
                        value={start}
                        onChange={(e) => setStart(e.target.value)}
                      />
                    </label>
                    <label>
                      Through
                      <input
                        type="date"
                        value={end}
                        onChange={(e) => setEnd(e.target.value)}
                      />
                    </label>
                    <button
                      disabled={!key || !instrument || !start || !end || busy}
                      onClick={() => void loadChart()}
                    >
                      Load chart
                    </button>
                  </div>
                  <Chart candles={candles} />
                  <div className="chart-footer">
                    Source: canonical market data{" "}
                    <span>Partial candles excluded</span>
                  </div>
                </section>
                <section className="panel">
                  <div className="panel-heading">
                    <h2>Pipeline health</h2>
                    <span className="tag">SYSTEM</span>
                  </div>
                  <div className="health-list">
                    {[
                      ["PostgreSQL", status?.services.database],
                      ["Redis", status?.services.redis],
                      ["Ingestion worker", status?.worker],
                      ["Market data feed", status?.feed],
                    ].map(([label, value]) => (
                      <div key={label}>
                        <span>{label}</span>
                        <span
                          className={`health-state ${["ready", "RUNNING", "CONNECTED"].includes(value ?? "") ? "healthy" : ""}`}
                        >
                          <span className="dot" />
                          {human(value ?? "unknown")}
                        </span>
                      </div>
                    ))}
                  </div>
                  <div className="pipeline-note">
                    <h3>Last complete candle</h3>
                    <p>
                      {status?.latest_candle
                        ? new Date(status.latest_candle).toLocaleString(
                            "en-IN",
                            { timeZone: "Asia/Kolkata" },
                          )
                        : "No validated history available"}
                    </p>
                    <p className="muted">
                      A running service does not establish data completeness.
                    </p>
                  </div>
                  <button
                    className="wide"
                    disabled={!key || busy}
                    onClick={() =>
                      void action(async () => {
                        const result = await request<{
                          authorization_url: string;
                        }>("/auth/upstox/start", key, {});
                        window.location.assign(result.authorization_url);
                      })
                    }
                  >
                    Connect Upstox ↗
                  </button>
                </section>
              </div>
              <section className="panel">
                <h2>Market Data Providers</h2>
                <button disabled={!key || busy} onClick={() => void action(async () => {
                  const result = await request<{authorization_url: string}>("/auth/sharekhan/start", key, {});
                  window.location.assign(result.authorization_url);
                })}>Connect Sharekhan</button>
                <label>Provider for new ingestion jobs
                  <select value={selectedProvider} onChange={e => setSelectedProvider(e.target.value)}>
                    <option value="">Configured default</option>
                    {providers.filter(p => p.enabled && p.capabilities.instrument_master).map(p =>
                      <option key={p.provider} value={p.provider}>{p.display_name}</option>)}
                  </select>
                </label>
                <div className="table-scroll"><table>
                  <thead><tr><th>Provider</th><th>Configured</th><th>Authentication</th><th>History</th><th>Live</th><th>WebSocket</th><th>Mappings</th><th>Last update</th></tr></thead>
                  <tbody>{providers.map(p => <tr key={p.provider}>
                    <td>{p.display_name}{p.preferred ? " (default)" : ""}{!p.enabled ? " (disabled)" : ""}</td>
                    <td>{p.configured ? "Yes" : "No"}</td><td>{human(p.authenticated)}</td>
                    <td>{p.capabilities.historical_candles ? "Available" : "Unavailable"}</td>
                    <td>{p.capabilities.websocket_quotes ? "Available" : "Unavailable"}</td>
                    <td>{human(p.websocket_status)}</td><td>{p.instrument_mappings ?? "Unknown"}</td>
                    <td>{p.last_successful_market_update ?? "Not verified"}</td>
                  </tr>)}</tbody>
                </table></div>
              </section>
              <section className="panel">
                <div className="panel-heading">
                  <div>
                    <h2>Ingestion activity</h2>
                    <p className="muted">
                      Durable jobs, explicit outcomes and recoverable history.
                    </p>
                  </div>
                  <div className="header-actions">
                    <button
                      disabled={!key || busy}
                      onClick={() =>
                        void action(async () => {
                          await request(`/instruments/sync${selectedProvider ? `?provider=${encodeURIComponent(selectedProvider)}` : ""}`, key, {});
                          setNotice("Instrument synchronization queued.");
                        })
                      }
                    >
                      Sync instruments
                    </button>
                    <button
                      className="primary"
                      disabled={!key || !instrument || !start || !end || busy}
                      onClick={() => void queueHistory()}
                    >
                      Ingest selected range
                    </button>
                  </div>
                </div>
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>JOB</th>
                        <th>TYPE</th>
                        <th>STATE</th>
                        <th>CREATED</th>
                        <th>DETAIL</th>
                      </tr>
                    </thead>
                    <tbody>
                      {jobs.map((j) => (
                        <tr key={j.id}>
                          <td className="mono">{j.id.slice(0, 8)}</td>
                          <td>{human(j.kind)}</td>
                          <td>
                            <span className="tag">{j.state}</span>
                          </td>
                          <td>
                            {new Date(j.created_at).toLocaleString("en-IN", {
                              timeZone: "Asia/Kolkata",
                            })}
                          </td>
                          <td>{j.error_code ?? "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {!jobs.length && (
                    <div className="table-empty">
                      No ingestion jobs yet. Synchronize the instrument master
                      to begin.
                    </div>
                  )}
                </div>
              </section>
              {page === "Settings" && (
                <section className="panel settings">
                  <h2>Exchange calendar</h2>
                  <p className="muted">
                    Import verified sessions as JSON. A holiday has null open
                    and close times. Unknown dates remain flagged.
                  </p>
                  <label htmlFor="calendar">Session records</label>
                  <textarea
                    id="calendar"
                    rows={6}
                    value={calendar}
                    onChange={(e) => setCalendar(e.target.value)}
                    placeholder='[{"exchange":"NSE","session_date":"YYYY-MM-DD","opens_at":null,"closes_at":null,"source":"verified source"}]'
                  />
                  <button
                    disabled={!key || busy || !calendar}
                    onClick={() =>
                      void action(async () => {
                        await request(
                          "/calendar/sessions",
                          key,
                          JSON.parse(calendar),
                        );
                        setNotice("Session calendar imported.");
                      })
                    }
                  >
                    Import sessions
                  </button>

                </section>
              )}
            </>
          )}
          <footer>
            STOCK INTELLIGENCE{" "}
            <span>
              Deterministic research infrastructure · No order execution
            </span>
          </footer>
        </div>
      </main>
    </div>
  );
}
