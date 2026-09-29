# Provider capabilities

Booleans mean implemented adapter functionality, not successful live authentication or account entitlement.
All implementations below are NOT LIVE VERIFIED in this phase.

| Capability | Upstox | Sharekhan | HDFC SKY |
|---|---|---|---|
| Instrument master | Yes, existing NSE cash/index | Yes, NC cash | No |
| Historical candles | Yes | Yes, 1m/daily retained window | No |
| Current-day candles | Yes | No, contract not verified | No |
| REST quotes / LTP | Yes | No, contract not found | No |
| WebSocket quotes / sampled ticks | Yes | Yes | No |
| Full depth | Yes, existing feed | No, only optional top-of-book parsing | No |
| OI | Yes | Yes, documented live field | No |
| Option chain | No | No | No |
| Orders | No | No | No |

GET /api/providers and GET /api/providers/{provider}/status require the operator key and return safe
configuration, capabilities, mapping counts, REST/WebSocket status and available update/error metadata.
NOT_VERIFIED is distinct from configured and from a recent market response. REST success markers expire
after a day and are not proof that a token is still valid. Missing Redis/database status is explicit.

Capability selection and configured provider priority permit partial providers. Unsupported capabilities
fail before transport calls. See SHAREKHAN.md and HDFC_SKY.md for source links and limitations.
