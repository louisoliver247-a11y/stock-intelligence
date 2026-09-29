# Trading VPS deployment

Deployed on 2026-09-29 to `200.234.43.221` (`srv1946265.hstgr.cloud`,
AlmaLinux 9 / CyberPanel). Target origin: `https://trading.caselawindia.io`.

The application is installed at `/opt/stock-intelligence`, with Python 3.12 in
`.venv` and the built frontend in `frontend/dist`. It runs as `stockapp`.
OpenLiteSpeed proxies the trading virtual host to `127.0.0.1:8080`.
The existing parent domain and other sites retain their routes.

The existing PostgreSQL server hosts a separate `stock_intelligence` database
and role. A separate authenticated Redis instance listens on `127.0.0.1:6381`.
Production secrets are generated on the server and stored in a protected `.env`;
they are not copied from the development machine or included in GitHub.
User accounts are stored in the production database. Broker credentials and
market data must be configured separately; live broker acceptance is pending.

## Services

These services start on boot and restart on failure:

```sh
systemctl status stock-intelligence-api stock-intelligence-worker stock-intelligence-redis
```

Local verification:

```sh
cd /opt/stock-intelligence
.venv/bin/python scripts/check_deployment.py --base-url http://127.0.0.1:8080
```

Deployment smoke checks and production login/create/delete/role/session tests
passed. DNS and public HTTPS were verified on 2026-09-29. Public administrator
login, user listing, and logout also passed with certificate verification enabled.

## DNS and HTTPS

In Hostinger's authoritative DNS zone for `caselawindia.io`, add:

| Type | Name | Value |
|---|---|---|
| A | trading | 200.234.43.221 |

Do not add an AAAA record unless IPv6 routing is configured for this app.
The `stock-intelligence-https.timer` checks public DNS every five minutes.
Once DNS resolves to the VPS, it invokes `scripts/enable_trading_https.py` to
request a Let's Encrypt certificate, configure the HTTPS listener mappings,
reload OpenLiteSpeed, and check readiness over verified HTTPS. HTTP redirects
to HTTPS; the ACME challenge path remains accessible. Certificate issuance
failures are throttled to one attempt per six hours.

```sh
systemctl start stock-intelligence-https.service
journalctl -u stock-intelligence-https --no-pager -n 30
```

Completion is recorded at `/var/lib/stock-intelligence/tls/complete`.
The certificate is installed under
`/etc/letsencrypt/live/trading.caselawindia.io/`. The
`stock-intelligence-certificate-renew.timer` runs acme.sh daily with its
service-created account home at `/.acme.sh`; successful renewal reloads
OpenLiteSpeed. The initial certificate expires 2026-12-28.
The server's CyberPanel-added `/etc/hosts` entries point to loopback, so the
automation deliberately queries public DNS rather than the local hosts file.

## Backups

`stock-intelligence-backup.timer` runs at 02:30 UTC daily. It writes database
dumps and configuration archives under `/var/backups/stock-intelligence`,
accessible only to root. The first backup passed. These are local backups;
the provider's existing weekly VPS backup remains separate. Monitor storage
and archive retention as market data grows.

Web-server configuration from before deployment is retained in
`/root/stock-intelligence-config-backup`. Do not restore the entire shared
configuration blindly after other websites have changed.

## Updating

Back up first. Pull the intended GitHub revision, install locked dependencies,
rebuild the frontend, run Alembic migrations, restart the API and worker, then
run the smoke check. Keep `.env`, database storage, and Redis storage intact.
Update the installed helper copies in `/usr/local/sbin` if their repository
versions change. When changing the domain later, update the virtual host,
certificate, `WEB_ORIGIN`, OAuth redirect configuration, and HTTPS helper.

