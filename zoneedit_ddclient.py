#!/usr/bin/env python3
"""
zoneedit_ddclient.py
Simple ZoneEdit DDClient updater

Disclaimer: This project is not affiliated with or supported by ZoneEdit. It was created by the maintainer as a replacement for `ddclient` on **RHEL 10** and other **RPM-based distributions** where `ddclient` is no longer supported.

Usage:
  - Configure `/etc/zoneedit_ddclient.ini` or pass `--config` with a config file path
  - Run once: `zoneedit_ddclient.py --once`
  - Run as daemon: `zoneedit_ddclient.py --daemon`

This script checks the public IP (IPv4) and updates ZoneEdit-hosted records.
Supports multiple hostnames (comma-separated) and uses account password.

How it works (high-level):
  - Read settings from a config file (default: `/etc/zoneedit_ddclient.ini`).
  - Determine current public IPv4 (via a configured service URL or local interface).
  - For each configured hostname, compare the discovered IP with a per-host
    state file stored in `state_dir` to avoid unnecessary updates.
  - If the IP changed, contact ZoneEdit's dynamic update endpoint to set the
    A record to the new IP. Successful updates are written to the state file.

Notes:
  - The script supports a `--dry-run` mode that shows what would be done
    without contacting ZoneEdit.
  - Daemon mode supports simple backoff handling when ZoneEdit returns rate
    limit responses.
"""

from __future__ import annotations
import argparse
import configparser
import logging
import os
import sys
import time
from pathlib import Path

try:
    import requests
except Exception:
    requests = None
    from urllib import request as urllib_request


DEFAULT_CONFIG_PATH = "/etc/zoneedit_ddclient.ini"
DEFAULT_STATE_DIR = "/var/lib/zoneedit_ddclient"
DEFAULT_USER_AGENT = "zoneedit-ddclient/1.0 (contact: admin)"
DEFAULT_ZONEEDIT_SERVER = "https://dynamic.zoneedit.com/auth/dynamic.html"


def get_public_ip(check_url: str = "https://api.ipify.org", use_web: bool = False) -> str:
    """Get public IPv4 address.

    If use_web is False, expect the service to return a plain IP in the body.
    If use_web is True, fetch the page and extract the first IPv4-looking string.

    Implementation notes:
      - Prefer the `requests` library when available for simpler API and
        clearer timeout/exception behavior; fallback to `urllib` otherwise.
      - The helper `_extract_ip` validates and normalizes an IPv4-like
        string from arbitrary text to prevent accepting malformed responses.
    """
    def _extract_ip(text: str) -> str:
        # Use a conservative regex to capture the first IPv4-looking string.
        import re

        m = re.search(r"(\d{1,3}(?:\.\d{1,3}){3})", text)
        if not m:
            # If no IP is found, the caller should treat this as a failure.
            raise RuntimeError("No IP address found in response")
        return m.group(1)

    # Fetch the IP-checking URL. We accept either a simple raw IP response
    # (e.g., api.ipify.org) or a web page from which we extract the IP.
    if requests:
        resp = requests.get(check_url, timeout=10)
        resp.raise_for_status()
        body = resp.text.strip()
    else:
        with urllib_request.urlopen(check_url, timeout=10) as resp:
            body = resp.read().decode().strip()

    # If the configured source is a web page, extract the IP from the HTML/text.
    if use_web:
        return _extract_ip(body)
    else:
        # plain body should be an IP; still validate/normalize using the helper
        return _extract_ip(body)



def get_ip_from_interface(ifname: str) -> str:
    """Get IPv4 address assigned to a local network interface on Linux.

    This uses an ioctl on a socket to query the interface address. It returns
    the IPv4 address string (e.g. "203.0.113.5"). Raises on failure.

    Notes:
      - This is a Linux-specific approach using `fcntl.ioctl` and will raise
        if those primitives are not available (e.g., on Windows).
      - The caller should catch exceptions and decide how to proceed.
    """
    import socket
    try:
        # These modules are platform-dependent; import errors are surfaced
        # as a RuntimeError to make the failure explicit to callers.
        import fcntl
        import struct
    except Exception as e:
        raise RuntimeError("Interface lookup not supported on this platform: %s" % e)

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # The SIOCGIFADDR ioctl (0x8915) returns binary-packed data containing
        # the address bytes at the standard offset. We unpack and convert to
        # a dotted-quad string using inet_ntoa.
        packed = fcntl.ioctl(s.fileno(), 0x8915, struct.pack('256s', ifname[:15].encode('utf-8')))
        return socket.inet_ntoa(packed[20:24])
    finally:
        s.close()


def read_last_ip(state_file: Path) -> str | None:
    try:
        return state_file.read_text().strip()
    except FileNotFoundError:
        return None


def write_last_ip(state_file: Path, ip: str) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(ip + "\n")


def update_zoneedit(hostname: str, username: str, password: str, ip: str, server: str = DEFAULT_ZONEEDIT_SERVER, user_agent: str = DEFAULT_USER_AGENT, dry_run: bool = False) -> tuple[bool, str]:
    """Call ZoneEdit dynamic update API for a single FQDN hostname.

    This function follows the working curl example: it sends the full FQDN in the
    `host` parameter (e.g. `host=blog.agonyweb.com`) and provides the `domain`
    separately (e.g. `domain=agonyweb.com`). This avoids situations where ZoneEdit
    rejects a bare host label.
    The `server` parameter may be either a full URL or a hostname; when a hostname is
    provided we assume HTTPS and append `/auth/dynamic.html`.
    """
    if "." not in hostname:
        return False, f"invalid hostname: {hostname}"

    # Use the full hostname as the `host` parameter (matches your curl example).
    host_param = hostname
    domain = hostname.split(".", 1)[1]
    import urllib.parse

    # normalize server into full URL
    if server.startswith("http://") or server.startswith("https://"):
        base = server.rstrip("/")
    else:
        base = f"https://{server}".rstrip("/")
    if not base.endswith("/auth/dynamic.html"):
        base = base + "/auth/dynamic.html"

    url = (
        f"{base}?host={urllib.parse.quote(host_param, safe='')}"
        f"&domain={urllib.parse.quote(domain, safe='')}"
        f"&username={urllib.parse.quote(username, safe='')}"
        f"&password={urllib.parse.quote(password, safe='')}"
        f"&ip={urllib.parse.quote(ip, safe='')}"
    )
    headers = {"User-Agent": user_agent}

    if dry_run:
        return True, f"DRYRUN: would call: {url}"

    if requests:
        resp = requests.get(url, headers=headers, auth=(username, password), timeout=10)
        text = resp.text.strip()
        code = resp.status_code
    else:
        # urllib
        req = urllib_request.Request(url, headers=headers)
        auth = (username + ":" + password).encode("utf-8")
        import base64

        req.add_header("Authorization", "Basic " + base64.b64encode(auth).decode())
        with urllib_request.urlopen(req, timeout=10) as r:
            text = r.read().decode().strip()
            code = r.getcode()

    # sanitize potential HTML in responses (some ZoneEdit responses include HTML fragments)
    try:
        import re

        # Keep original text for XML parsing, but also produce a cleaned text for logs
        text_clean = re.sub(r"<[^>]+>", "", text).strip()

        # Check for ZoneEdit XML error payloads like:
        # <ERROR CODE="702" PARAM="600" TEXT="Minimum 600 seconds between requests" ZONE="test.agonyweb.com">
        m = re.search(r'<ERROR[^>]*CODE\s*=\s*"(?P<code>\d+)"[^>]*PARAM\s*=\s*"(?P<param>\d+)"[^>]*TEXT\s*=\s*"(?P<text>[^"]+)"', text, re.IGNORECASE)
        if not m:
            # fallback: look for an ERROR tag with at least a CODE attribute
            m = re.search(r'<ERROR[^>]*CODE\s*=\s*"(?P<code>\d+)"[^>]*TEXT\s*=\s*"(?P<text>[^"]+)"', text, re.IGNORECASE)

        if m:
            err_code = m.groupdict().get('code')
            err_text = m.groupdict().get('text', '').strip()
            err_param = m.groupdict().get('param')

            if err_code == '702':
                # Rate-limit: suggest waiting or increasing the configured interval
                if err_param:
                    return False, f"RATE_LIMIT: {err_text} (retry after {err_param}s)"
                else:
                    return False, f"RATE_LIMIT: {err_text}"

            if err_code == '709':
                # Invalid hostname: host not present or not owned by credentials used
                return False, f"INVALID_HOST: {err_text} (verify host exists under the account used for this update, or use correct credentials)"

            # Generic ZoneEdit error
            return False, f"ZONEEDIT_ERROR {err_code}: {err_text}"

    except Exception:
        text_clean = text

    if code != 200:
        return False, f"HTTP {code}: {text_clean}"

    # ZoneEdit response examples are simple text messages; return cleaned text for logging
    return True, text_clean


def load_config(path: str) -> dict:
    # Read basic configuration from the supplied INI file path.
    # Expected file contains a [zoneedit] section with keys such as:
    #   hostnames, username, password, check_ip_service, interval, state_dir, etc.
    # We normalize `hostnames` into a list and provide sensible defaults for
    # optional values to make later code simpler.
    config = configparser.ConfigParser()
    config.read(path)
    if "zoneedit" not in config:
        raise SystemExit(f"Missing [zoneedit] section in config: {path}")

    c = config["zoneedit"]
    hostnames = c.get("hostnames", c.get("hostname", ""))
    hosts = [h.strip() for h in hostnames.split(",") if h.strip()]

    # Return a dict with normalized keys consumed by run_once / daemon logic
    return {
        "hostnames": hosts,
        "username": c.get("username"),
        "password": c.get("password"),
        "check_ip_service": c.get("check_ip_service", "https://api.ipify.org"),
        "use": c.get("use", None),
        "web": c.get("web", None),
        "server": c.get("server", DEFAULT_ZONEEDIT_SERVER),
        "protocol": c.get("protocol", None),
        "interval": c.getint("interval", fallback=300),
        "state_dir": c.get("state_dir", DEFAULT_STATE_DIR),
        "interface": c.get("interface", None),
        "user_agent": c.get("user_agent", DEFAULT_USER_AGENT),
    }


def setup_logging(debug: bool) -> None:
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s: %(message)s")


def process_host(hostname: str, username: str, password: str, ip: str, state_dir: Path, user_agent: str, server: str, dry_run: bool = False) -> tuple[bool, str]:
    """Process a single hostname: check last IP, call ZoneEdit if needed, write last IP.

    Returns tuple (ok, message). Messages may be:
      - 'UNCHANGED' when IP matches last recorded
      - response text from server on success
      - error text on failure (e.g., RATE_LIMIT)

    Steps:
      1. Determine the per-host state file path and read the last recorded IP.
      2. If IP hasn't changed, skip the update and return 'UNCHANGED'.
      3. Otherwise, call update_zoneedit and on success write the new IP.
      4. If ZoneEdit rejects due to rate limiting, attempt a DNS lookup to see
         if the DNS already reflects the desired IP; if so treat as success.
    """
    state_file = state_dir / (hostname.replace("/", "_") + ".last_ip")
    last_ip = read_last_ip(state_file)

    # No-op if the IP is unchanged compared with our last recorded state
    if ip == last_ip:
        return True, "UNCHANGED"

    ok, msg = update_zoneedit(hostname, username, password, ip, server=server, user_agent=user_agent, dry_run=dry_run)
    if ok:
        # On success, persist the new IP unless this was just a dry-run
        if not dry_run:
            write_last_ip(state_file, ip)
        return True, msg
    else:
        # Special handling: if ZoneEdit returned a rate-limit error we may still
        # have a successful prior update in DNS. If DNS resolves to our target
        # IP, treat this as effectively up-to-date and persist the state.
        if "RATE_LIMIT" in msg.upper():
            try:
                import socket

                dns_ip = socket.gethostbyname(hostname)
                if dns_ip == ip:
                    if not dry_run:
                        write_last_ip(state_file, ip)
                    return True, f"RATE_LIMIT_BUT_DNS_MATCH: {dns_ip}"
            except Exception:
                # If DNS lookup fails, continue and return the original error
                pass

        return False, msg


def run_once(cfg: dict, dry_run: bool = False) -> bool:
    hostnames = cfg["hostnames"]
    username = cfg["username"]
    password = cfg["password"]
    check_service = cfg["check_ip_service"]
    use = cfg.get("use")
    web = cfg.get("web")
    server = cfg.get("server", DEFAULT_ZONEEDIT_SERVER)
    state_dir = Path(cfg["state_dir"]).expanduser()
    user_agent = cfg["user_agent"]

    if not (hostnames and username and password):
        logging.error("Config missing hostnames/username/password")
        return False

    interface = cfg.get("interface")
    if interface:
        try:
            ip = get_ip_from_interface(interface)
            logging.info("Using IP from interface %s: %s", interface, ip)
        except Exception as e:
            logging.exception("Failed to get IP from interface %s: %s", interface, e)
            return False
    else:
        try:
            if use and use.lower() == "web" and web:
                ip = get_public_ip(web, use_web=True)
            else:
                ip = get_public_ip(check_service)
        except Exception as e:
            logging.exception("Failed to detect public IP: %s", e)
            return False

    all_ok = True
    for hostname in hostnames:
        ok, msg = process_host(hostname, username, password, ip, state_dir, user_agent, server, dry_run=dry_run)
        if ok:
            if msg == "UNCHANGED":
                logging.info("IP unchanged for %s (%s). No update needed.", hostname, ip)
            else:
                logging.info("Update response for %s: %s", hostname, msg)
        else:
            logging.error("Update failed for %s: %s", hostname, msg)
            all_ok = False

    return all_ok


def main() -> int:
    p = argparse.ArgumentParser(description="ZoneEdit DDClient updater")
    p.add_argument("--config", "-c", default=DEFAULT_CONFIG_PATH, help="Path to config file")
    p.add_argument("--once", action="store_true", help="Run once and exit")
    p.add_argument("--daemon", action="store_true", help="Run continuously (interval from config)")
    p.add_argument("--dry-run", action="store_true", help="Show actions without contacting ZoneEdit")
    p.add_argument("--debug", action="store_true", help="Enable debug logging")
    p.add_argument("--interface", "-i", help="Network interface to use for IP (overrides config)")
    p.add_argument("--no-backoff", action="store_true", help="Disable backoff behavior on rate limit in daemon mode")
    p.add_argument("--backoff-max", type=int, default=None, help="Maximum backoff seconds (overrides config)")

    args = p.parse_args()

    setup_logging(args.debug)

    if not os.path.exists(args.config):
        logging.error("Config file not found: %s", args.config)
        return 2

    cfg = load_config(args.config)

    # CLI override for interface
    if args.interface:
        cfg["interface"] = args.interface

    if args.once:
        return 0 if run_once(cfg, dry_run=args.dry_run) else 1

    if args.daemon:
        interval = cfg.get("interval", 300)
        backoff_cfg = cfg.get("backoff", True)
        backoff_enabled = not args.no_backoff and backoff_cfg
        backoff_max = args.backoff_max if args.backoff_max is not None else cfg.get("backoff_max", 3600)

        logging.info("Starting daemon mode: checking every %s seconds (backoff=%s, backoff_max=%s)", interval, backoff_enabled, backoff_max)

        # next_allowed tracks per-host timestamps when they may be retried
        next_allowed: dict[str, float] = {}

        try:
            while True:
                # detect current IP once per iteration
                interface = cfg.get("interface")
                try:
                    if interface:
                        ip = get_ip_from_interface(interface)
                        logging.info("Using IP from interface %s: %s", interface, ip)
                    else:
                        use = cfg.get("use")
                        web = cfg.get("web")
                        check_service = cfg.get("check_ip_service")
                        if use and use.lower() == "web" and web:
                            ip = get_public_ip(web, use_web=True)
                        else:
                            ip = get_public_ip(check_service)
                except Exception as e:
                    logging.exception("Failed to detect public IP: %s", e)
                    time.sleep(interval)
                    continue

                now = time.time()
                for hostname in cfg["hostnames"]:
                    na = next_allowed.get(hostname, 0)
                    if now < na:
                        logging.info("Skipping %s due to backoff until %s", hostname, time.ctime(na))
                        continue

                    ok, msg = process_host(hostname, cfg["username"], cfg["password"], ip, Path(cfg["state_dir"]).expanduser(), cfg["user_agent"], cfg.get("server", DEFAULT_ZONEEDIT_SERVER), dry_run=args.dry_run)
                    if ok:
                        if msg == "UNCHANGED":
                            logging.info("IP unchanged for %s (%s). No update needed.", hostname, ip)
                        else:
                            logging.info("Update response for %s: %s", hostname, msg)
                    else:
                        logging.error("Update failed for %s: %s", hostname, msg)

                        # backoff trigger: look for RATE_LIMIT or explicit retry info
                        import re

                        m = re.search(r"RETRY AFTER (\d+)S", msg.upper()) or re.search(r"retry after (\d+)s", msg, re.IGNORECASE)
                        delay = None
                        if m:
                            try:
                                delay = int(m.group(1))
                            except Exception:
                                delay = None

                        # also handle our RATE_LIMIT: ... (retry after 600s) pattern
                        if delay is None:
                            m2 = re.search(r"retry after\s*(\d+)s", msg, re.IGNORECASE)
                            if m2:
                                delay = int(m2.group(1))

                        # if we detected a rate limit and backoff is enabled, set next_allowed
                        if delay and backoff_enabled:
                            delay = min(delay, backoff_max)
                            next_allowed[hostname] = now + delay
                            logging.warning("Applying backoff for %s: %ss (until %s)", hostname, delay, time.ctime(next_allowed[hostname]))

                time.sleep(interval)
        except KeyboardInterrupt:
            logging.info("Shutting down daemon")
            return 0

    # Default to once
    return 0 if run_once(cfg, dry_run=args.dry_run) else 1


if __name__ == "__main__":
    sys.exit(main())
