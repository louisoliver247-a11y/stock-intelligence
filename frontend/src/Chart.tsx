import { useEffect, useRef } from "react";
import {
  CandlestickSeries,
  ColorType,
  createChart,
  type UTCTimestamp,
} from "lightweight-charts";
import type { Candle } from "./api";

export function Chart({ candles }: { candles: Candle[] }) {
  const container = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!container.current || !candles.length) return;
    const chart = createChart(container.current, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: "#121b25" },
        textColor: "#a3b4c4",
      },
      grid: {
        vertLines: { color: "#1c2936" },
        horzLines: { color: "#1c2936" },
      },
      timeScale: { timeVisible: true },
      localization: {
        timeFormatter: (time: number) =>
          new Date(time * 1000).toLocaleString("en-IN", {
            timeZone: "Asia/Kolkata",
          }),
      },
    });
    const series = chart.addSeries(CandlestickSeries, {
      upColor: "#6abfa1",
      downColor: "#d48585",
      borderVisible: false,
      wickUpColor: "#6abfa1",
      wickDownColor: "#d48585",
    });
    series.setData(
      candles.map((c) => ({
        time: (Date.parse(c.timestamp) / 1000) as UTCTimestamp,
        open: Number(c.open),
        high: Number(c.high),
        low: Number(c.low),
        close: Number(c.close),
      })),
    );
    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [candles]);
  return (
    <div className="chart" ref={container}>
      {!candles.length && (
        <div className="empty">
          <span className="empty-icon">▥</span>
          <h3>No validated candles loaded</h3>
          <p>
            Synchronize instruments and ingest history to inspect real price
            data.
          </p>
        </div>
      )}
    </div>
  );
}
