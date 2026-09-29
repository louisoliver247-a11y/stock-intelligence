"""Offline JSON analysis; no network, broker credentials or automatic live enablement."""

import argparse
import json
from datetime import datetime
from pathlib import Path

from analysis.indicators import ALGORITHM_VERSION, calculate_series
from config.indicators import IndicatorConfig
from market_data.calendar import SessionCalendar
from market_data.providers.models import CandleObservation, ExchangeSession


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candles", type=Path, required=True, help="JSON array of candle/known_at/revision records")
    parser.add_argument("--sessions", type=Path, required=True, help="JSON array of explicit exchange sessions")
    parser.add_argument("--as-of", type=datetime.fromisoformat, required=True, help="Timezone-aware cutoff")
    parser.add_argument("--config", type=Path, help="Optional IndicatorConfig JSON object")
    parser.add_argument("--output", type=Path, required=True, help="New output file; existing files are never replaced")
    args = parser.parse_args()
    try:
        config = IndicatorConfig.model_validate_json(args.config.read_text()) if args.config else IndicatorConfig()
        sessions = [ExchangeSession.model_validate(row) for row in json.loads(args.sessions.read_text())]
        observations = [CandleObservation.model_validate(row) for row in json.loads(args.candles.read_text())]
        if not observations:
            raise ValueError("EMPTY_INPUT")
        snapshots = [snapshot.model_dump(mode="json") for snapshot in calculate_series(
            observations, SessionCalendar(sessions), as_of=args.as_of, config=config)]
        document = {"algorithm_version": ALGORITHM_VERSION, "mode": "OFFLINE_RESEARCH",
                    "live_integrity": "NOT_VERIFIED", "config": config.model_dump(mode="json"),
                    "snapshots": snapshots}
        serialized = json.dumps(document, indent=2, allow_nan=False)
        with args.output.open("x", encoding="utf-8") as output:
            output.write(serialized + "\n")
        print(f"Wrote {len(snapshots)} snapshots to {args.output}; live analysis remains disabled.")
    except (ValueError, OSError, TypeError) as exc:
        parser.exit(2, f"Indicator analysis failed: {exc}\n")


if __name__ == "__main__":
    main()
