import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import App from "./App";

vi.mock("./Chart", () => ({
  Chart: () => <div>No validated candles loaded</div>,
}));

describe("foundation terminal", () => {
  it("shows unknown data and the integrity gate without invented metrics", () => {
    render(<App />);
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
      if (url.includes("/market/status")) data = {services: {}, counts: {}};
      if (url.includes("/instruments?")) data = Array.from({length: 50}, (_, i) => ({
        instrument_id: String(i), symbol: `TEST${i}`, exchange: "NSE", name: "Test",
      }));
      return {ok: true, json: async () => data};
    });
    vi.stubGlobal("fetch", fetchMock);
    try {
      render(<App />);
      fireEvent.change(screen.getByLabelText("Operator API key"), {target: {value: "x".repeat(32)}});
      fireEvent.click(screen.getByRole("button", {name: /^Connect$/}));
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
