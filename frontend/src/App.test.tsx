import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";

vi.mock("./Chart", () => ({
  Chart: () => <div>No validated candles loaded</div>,
}));

afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

function mockApi() {
  const fetcher = vi.fn(async (url: string) => {
    let data: unknown = [];
    if (url.includes("/auth/login")) data = {token: "session-token"};
    if (url.includes("/market/status")) data = {services: {}, counts: {}};
    return {ok: true, json: async () => data};
  });
  vi.stubGlobal("fetch", fetcher);
  return fetcher;
}
async function signIn() {
  fireEvent.change(screen.getByLabelText("Email address"), {target: {value: "test@example.com"}});
  fireEvent.change(screen.getByLabelText("Password"), {target: {value: "test-password"}});
  fireEvent.click(screen.getByRole("button", {name: "Sign in"}));
  await screen.findByRole("navigation", {name: "Primary navigation"});
}

describe("foundation terminal", () => {
  it("shows only the sign-in page before authentication", () => {
    const fetcher = mockApi();
    render(<App />);
    expect(screen.getByRole("heading", {name: "Welcome back"})).toBeInTheDocument();
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
    expect(screen.queryByText("Integrity gate: not verified")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Operator API key")).not.toBeInTheDocument();
    expect(fetcher).not.toHaveBeenCalled();
  });
  it("keeps the app hidden after invalid credentials", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ok: false, status: 401, json: async () => ({detail: "INVALID_EMAIL_OR_PASSWORD"})})));
    render(<App />);
    fireEvent.change(screen.getByLabelText("Email address"), {target: {value: "test@example.com"}});
    fireEvent.change(screen.getByLabelText("Password"), {target: {value: "wrong-password"}});
    fireEvent.click(screen.getByRole("button", {name: "Sign in"}));
    expect(await screen.findByRole("alert")).toHaveTextContent("email or password is incorrect");
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
  });
  it("opens the app after login and removes it on logout", async () => {
    mockApi(); render(<App />); await signIn();
    fireEvent.click(screen.getByRole("button", {name: "Sign out"}));
    await screen.findByRole("heading", {name: "Welcome back"});
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
  });
  it("returns to sign-in when a protected request rejects an expired session", async () => {
    const fetcher = mockApi(); render(<App />); await signIn();
    fetcher.mockImplementation(async () => ({ok: false, status: 401, json: async () => ({detail: "SESSION_EXPIRED_OR_INVALID"})}));
    fireEvent.click(screen.getByRole("button", {name: /Refresh/}));
    await screen.findByRole("heading", {name: "Welcome back"});
    expect(screen.getByRole("status")).toHaveTextContent("session has expired");
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
  });
  it("shows unknown data and the integrity gate without invented metrics", async () => {
    mockApi(); render(<App />); await signIn();
    expect(
      screen.getByText("Integrity gate: not verified"),
    ).toBeInTheDocument();
    expect(screen.getByText("UNKNOWN")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Ingest selected range" }),
    ).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: /Scanner/ }));
    expect(
      screen.getByText("Scanner is scheduled for a later milestone"),
    ).toBeInTheDocument();
  });
  it("searches and paginates instruments on the server", async () => {
    cleanup();
    const fetchMock = vi.fn(async (url: string) => {
      let data: unknown = [];
      if (url.includes("/auth/login")) data = {token: "session-token"};
      if (url.includes("/market/status")) data = {services: {}, counts: {}};
      if (url.includes("/instruments?")) data = Array.from({length: 50}, (_, i) => ({
        instrument_id: String(i), symbol: `TEST${i}`, exchange: "NSE", name: "Test",
      }));
      return {ok: true, json: async () => data};
    });
    vi.stubGlobal("fetch", fetchMock);
    try {
      render(<App />);
      await signIn();
      await waitFor(() => expect(screen.getByRole("button", {name: "Next instruments"})).toBeEnabled());
      fireEvent.click(screen.getByRole("button", {name: "Next instruments"}));
      await waitFor(() => expect(fetchMock.mock.calls.some(([url]) => url.includes("offset=50"))).toBe(true));
      fireEvent.change(screen.getByPlaceholderText("Symbol, name or ISIN"), {target: {value: "RELIANCE"}});
      await waitFor(() => expect(fetchMock.mock.calls.some(([url]) =>
        url.includes("q=RELIANCE") && url.includes("offset=0") && url.includes("active=true"))).toBe(true));
    } finally {
      cleanup();
      vi.unstubAllGlobals();
    }
  });
});
