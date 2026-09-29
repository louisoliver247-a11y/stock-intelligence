# HDFC SKY

Capability descriptor IMPLEMENTED; market-data adapter functionality NOT IMPLEMENTED / NOT VERIFIED.
All operational capabilities remain false, including orders. Enabling the descriptor cannot invent access.

Official sources inspected 2026-09-27:
- https://developer.hdfcsky.com/
- https://hdfcsky.com/algo-trading
- https://hdfcsky.com/blogs/trading-strategies/hdfc-sky-open-api-guide

The developer landing page labels Market Data and Websockets as coming soon while other official pages
advertise them. Inspection of the public application did not establish a usable external endpoint and
payload contract. Promotional claims are not sufficient to implement an API. No HDFC account credentials
were configured. This does not establish that a capability is unavailable to every HDFC customer.

| Capability | Classification in inspected technical material |
|---|---|
| Authentication contract | NOT_DOCUMENTED |
| Instrument master | NOT_DOCUMENTED |
| Historical candles | NOT_DOCUMENTED |
| REST quotes | NOT_DOCUMENTED |
| REST LTP | NOT_DOCUMENTED |
| WebSocket contract | NOT_DOCUMENTED |
| Market-depth payload | NOT_DOCUMENTED |
| Open-interest payload | NOT_DOCUMENTED |

The typed classification model also supports SUPPORTED_AND_IMPLEMENTED,
SUPPORTED_BUT_NOT_IMPLEMENTED, DOCUMENTED_BUT_ACCESS_UNVERIFIED and UNAVAILABLE.
No endpoint, normalization fixture or WebSocket implementation was fabricated. HDFC-origin indicator
fixtures verify provider independence only; they do not verify HDFC API payloads.

Manual action: obtain current account-accessible official developer specifications and market-data
entitlements. Supply documentation without sharing credentials in chat. Credentials must remain backend
environment/token storage. Then implement and mock-test only those confirmed contracts before live testing.
