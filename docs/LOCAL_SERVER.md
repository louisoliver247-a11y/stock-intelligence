# Windows local server

Open http://localhost:8080. The frontend and API share one loopback-only server.

- Double-click `Start Local App.cmd` to start the services and open the browser.
- Paste the operator key into the workspace connection form. Start copies it to
  the clipboard; `Copy Operator Key.cmd` copies it again without restarting.
- Double-click `Stop Local App.cmd` to stop services while preserving data.
- After restarting Windows, run the start shortcut again.

## Installed local services

| Service | Address | Storage |
| --- | --- | --- |
| Frontend / FastAPI | localhost:8080 | frontend/dist |
| PostgreSQL 16 | 127.0.0.1:55433 | ../.tools/local-pgdata |
| Redis 7.4.11 Windows build | 127.0.0.1:56379 | .local/redis-data |
| Background ingestion worker | No listening port | PostgreSQL jobs |

Database and Redis require generated passwords. Local credentials are in the
ignored `.env.local`; Docker's `.env` is preserved. Logs and process identities
are in the ignored `.local` directory. Stop validates process creation times
before acting on saved PIDs. PostgreSQL and Redis shut down through their native
interfaces. Repeated start commands reuse running processes.

This deployment uses regular PostgreSQL, which the existing migrations support.
Timescale hypertables and Docker are not part of this Windows-local runtime.
The Redis binary is the community Windows build from
https://github.com/redis-windows/redis-windows/releases/tag/7.4.11 .
The downloaded MSYS2 archive was checked against the release's SHA256:
`EC629971D76756DD040204297F1A92F43848E7A5F4862D39426BEEAFCCA2A2A9`.

## Prepared data

The public instrument-master job imported 9,885 NSE equities/index instruments.
No synthetic price candles were inserted into this local database.

`config/calendars/nse-2026-09.json` contains September 2026 only: 21 normal
09:15–15:30 IST sessions and nine closures, including September 14.
Sources reviewed on September 25, 2026:

- [NSE capital-market holiday circular CMTR/71775](https://nsearchives.nseindia.com/content/circulars/CMTR71775.pdf)
- [NSE normal equity trading hours](https://www.nseindia.com/static/market-data/market-timings)

Dates outside that month require additional reviewed sessions. This schedule
does not certify actual historical feed continuity or capture unannounced halts.

## Connect Upstox when ready

1. Put `UPSTOX_CLIENT_ID` and `UPSTOX_CLIENT_SECRET` in `.env.local`.
2. Register `http://localhost:8080/api/auth/upstox/callback` in the Upstox app.
3. Stop and restart the local app, then use Settings to connect Upstox.
   Alternatively configure the backend `UPSTOX_ACCESS_TOKEN` in `.env.local`.
4. Queue a small historical range within the imported September calendar, check
   the job result and quality issues, and load the chart.

Live feed subscriptions remain opt-in and require a configured instrument list
and Upstox credentials. The offline indicator engine is available separately;
later scanner/strategy/portfolio features remain outside the implemented scope.

## Checks

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/local.ps1 status
```

`docs/LOCAL_DEPLOYMENT_CHECK.json` records the first successful local smoke check.
All five checks passed: frontend, liveness, PostgreSQL/Redis readiness,
unauthenticated access rejection, and authenticated worker status.
Clean restart and repeated start were also verified, preserving the instrument
master. Full backend validation used a separate disposable database.
