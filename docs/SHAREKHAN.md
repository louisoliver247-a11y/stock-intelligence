# Mirae Asset Sharekhan

IMPLEMENTED / TESTED WITH MOCKS. NOT LIVE VERIFIED: no local credentials or stored broker tokens.

Official sources inspected 2026-09-27:
- https://www.sharekhan.com/trading-api/documentation/login-and-user-details
- https://www.sharekhan.com/trading-api/documentation/script-master
- https://www.sharekhan.com/trading-api/documentation/historical-api
- https://www.sharekhan.com/trading-api/documentation/web-socket-api
- https://www.sharekhan.com/faq
- https://github.com/Sharekhan-API/shareconnectpython
- https://github.com/Sharekhan-API/shareconnectnodejs/blob/main/lib/sharekhan-api.js

The website dynamically serves documentation through AlgoDocs/showdesc. Endpoint/payload contracts
were read there, not inferred from unofficial examples. The Node SDK confirms data.token extraction.

Implemented scope: version-1005 browser-bound login, authenticated GCM token transformation, encrypted
backend token storage, NC (NSE cash) ScripMaster, 1minute/daily history, JSON live quotes, cumulative
volume and OI, unsubscription, reconnect/resubscription and bounded buffering. Historical prices remain
unadjusted, explicitly tagged. The history endpoint exposes a retained window rather than documented
start/end parameters; the adapter filters locally. Missing requested minutes remain quality issues.
NSE derivatives and other exchanges are not enabled; canonical schema supports future derivative identity.

REST quote/LTP endpoints and a current-day reconciliation contract were not established in the
inspected docs. Those capabilities are disabled. Live quotes/LTP are available through WebSocket.
Top-of-book fields are parsed when supplied; full market-depth capability is disabled because a complete
level payload contract was not verified. No order/ack subscription or order endpoint is implemented.

Configuration: ENABLE_SHAREKHAN=true, SHAREKHAN_API_KEY, SHAREKHAN_SECRET_KEY (32-byte provider
secret), and TOKEN_ENCRYPTION_KEY for browser authentication. Register the backend callback
/api/auth/sharekhan/callback with the broker. SHAREKHAN_ACCESS_TOKEN may be supplied instead for
manual backend token configuration. No invented client ID or redirect request parameter is sent.
POST /api/auth/sharekhan/start requires the operator key; callback state is single-use and browser-bound.
The broker's login protocol puts its API identifier in the broker redirect URL; secure key and access
token never enter frontend application storage or source. Keep access logs disabled as configured.

REST retries are bounded, with conservative per-adapter pacing. A 429 or transient server/network
failure retries with backoff. This is not a global account-wide rate limiter across several deployments.
WebSocket TLS verification remains enabled; official SDK examples that disable it were not followed.

Acceptance still required: login, one instrument, a small history request, one live quote, one small
subscription, timestamp/volume comparison and disconnect recovery against a real account.
