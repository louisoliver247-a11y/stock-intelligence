"""Finish this VPS's HTTPS setup after the trading DNS record becomes available.

Installed as a root systemd oneshot on srv1946265; no credentials in this file.
"""
import ipaddress
import re
import subprocess
import time
from pathlib import Path

DOMAIN = "trading.caselawindia.io"
SERVER_IP = "200.234.43.221"
STATE = Path("/var/lib/stock-intelligence/tls")
CERT_DIR = Path(f"/etc/letsencrypt/live/{DOMAIN}")
VHOST = Path(f"/usr/local/lsws/conf/vhosts/{DOMAIN}/vhost.conf")
MAIN = Path("/usr/local/lsws/conf/httpd_config.conf")


def run(*args):
    subprocess.run(args, check=True, timeout=300)


def main():
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    if (STATE / "complete").exists():
        print("HTTPS setup already completed; acme.sh manages renewal.")
        return
    # CyberPanel adds loopback entries to /etc/hosts. Query public DNS directly.
    addresses = set()
    for record in ("A", "AAAA"):
        result = subprocess.run(
            ["dig", "+short", "+time=3", "+tries=1", "@1.1.1.1", DOMAIN, record],
            capture_output=True, text=True, timeout=10, check=True,
        )
        for value in result.stdout.splitlines():
            try:
                addresses.add(str(ipaddress.ip_address(value.strip())))
            except ValueError:
                continue
    if addresses != {SERVER_IP}:
        print(f"Waiting for DNS to point exclusively to {SERVER_IP}; found {sorted(addresses)}")
        return
    attempted = STATE / "last-attempt"
    if attempted.exists() and time.time() - attempted.stat().st_mtime < 21600:
        print("Waiting before retrying certificate issuance.")
        return
    attempted.touch()
    acme = "/root/.acme.sh/acme.sh"
    run(acme, "--issue", "--server", "letsencrypt", "-d", DOMAIN,
        "--webroot", "/usr/local/lsws/Example/html", "--keylength", "ec-256")
    CERT_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    run(acme, "--install-cert", "-d", DOMAIN, "--ecc",
        "--key-file", str(CERT_DIR / "privkey.pem"),
        "--fullchain-file", str(CERT_DIR / "fullchain.pem"),
        "--reloadcmd", "systemctl reload lsws")
    before_vhost, before_main = VHOST.read_text(), MAIN.read_text()
    (STATE / "vhost.before-tls.conf").write_text(before_vhost)
    (STATE / "httpd.before-tls.conf").write_text(before_main)
    if "vhssl" not in before_vhost:
        VHOST.write_text(before_vhost + f"""
vhssl {{
  keyFile {CERT_DIR}/privkey.pem
  certFile {CERT_DIR}/fullchain.pem
  certChain 1
  sslProtocol 24
  enableECDHE 1
  renegProtection 1
  sslSessionCache 1
  enableSpdy 15
}}
""")

    def map_listener(match):
        block = match.group()
        if re.search(r"\bsecure\s+1\b", block) and DOMAIN not in block:
            block = block.replace("{", f"{{\n  map {DOMAIN} {DOMAIN}", 1)
        return block

    MAIN.write_text(re.sub(r"listener\s+[^{}]+\{[^{}]*\}", map_listener, before_main))
    checked = subprocess.run(["/usr/local/lsws/bin/lshttpd", "-t"], capture_output=True, text=True)
    # This CyberPanel build returns 1 for its baseline license warning too.
    if "[ERROR]" in checked.stdout + checked.stderr:
        VHOST.write_text(before_vhost)
        MAIN.write_text(before_main)
        raise RuntimeError("Web server configuration rejected; previous configuration restored")
    run("systemctl", "reload", "lsws")
    run("curl", "--fail", "--silent", "--show-error", "--retry", "5", "--retry-connrefused",
        "--resolve", f"{DOMAIN}:443:127.0.0.1", f"https://{DOMAIN}/api/health/ready")
    (STATE / "complete").touch()
    print(f"\nHTTPS ready: https://{DOMAIN}")


if __name__ == "__main__":
    main()
