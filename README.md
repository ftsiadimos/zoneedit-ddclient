# ZoneEdit DDClient Updater 🔧

**Disclaimer:** This project is not affiliated with or supported by ZoneEdit. It was created by the maintainer as a replacement for `ddclient` on **RHEL 10** and other **RPM-based distributions** where `ddclient` is no longer supported.

Description

ZoneEdit DDClient Updater is a lightweight Python service that keeps A records hosted on ZoneEdit in sync with your current public IPv4. It can run once for an immediate update or run as a long-lived systemd-managed daemon to periodically verify and update your IP. The service supports reading the IP from a local network interface or from an external check service, per-host state files to avoid unnecessary updates, a dry-run mode, and simple backoff when ZoneEdit signals rate limits.

Install via RPM

A pre-built RPM is included in the `dist/` directory. Install it with:

```bash
sudo dnf install ./dist/noarch/zoneedit-ddclient-1.0-1.noarch.rpm
# or with rpm:
sudo rpm -Uvh dist/noarch/zoneedit-ddclient-1.0-1.noarch.rpm
```

The package installs the executable to `/usr/bin/zoneedit_ddclient`, the example config to `/etc/zoneedit_ddclient.ini.example`, and a `systemd` unit `zoneedit-ddclient.service`.

Quick start:

1. Copy the example config to `/etc/zoneedit_ddclient.ini` and edit it (use the `[zoneedit]` section):
   ```bash
   sudo cp /etc/zoneedit_ddclient.ini.example /etc/zoneedit_ddclient.ini
   sudo nano /etc/zoneedit_ddclient.ini
   ```

2. Configure the essential values in `/etc/zoneedit_ddclient.ini`:
   - `hostnames` (comma-separated FQDNs to update)
   - `username` (ZoneEdit account email)
   - `password` (ZoneEdit account password)
   - Optionally set `interface` to use a local interface IP instead of querying an external service, or set `check_ip_service`/`use=web`.

3. Create the state directory and set ownership if running as a non-root user:
   ```bash
   sudo mkdir -p /var/lib/zoneedit_ddclient
   sudo chown youruser:youruser /var/lib/zoneedit_ddclient
   ```

4. Start and enable the systemd service:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now zoneedit-ddclient.service
```

   Alternatively, test a one-shot run before enabling the service:
   ```bash
   sudo /usr/bin/zoneedit_ddclient --config /etc/zoneedit_ddclient.ini --once

2. (Optional) Create the state directory and set ownership if running as non-root:
   ```bash
   sudo mkdir -p /var/lib/zoneedit_ddclient
   sudo chown youruser:youruser /var/lib/zoneedit_ddclient
   ```

3. Run once to test:
   ```bash
   python3 zoneedit_ddclient.py --config /etc/zoneedit_ddclient.ini --once
   # or use a specific interface (overrides config):
   python3 zoneedit_ddclient.py --config /etc/zoneedit_ddclient.ini --interface eth0 --once
   ```

4. Install systemd service (optional):
   ```bash
   sudo cp zoneedit-ddclient.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now zoneedit-ddclient.service
   ```

Notes:
- The script supports `--dry-run` to preview the update call without sending credentials.
- ZoneEdit enforces a minimum interval between updates (commonly 600 seconds). Set `interval` in your config to at least 600 to avoid rate-limit errors like `Minimum 600 seconds between requests`.
- The daemon supports exponential backoff when ZoneEdit signals rate limits; this is on by default. Use `--no-backoff` to disable or set `backoff_max` in the config to limit the maximum backoff (seconds).
- You can specify a local network interface to use its IPv4 address instead of querying an external service: set `interface = eth0` in the config or pass `--interface eth0`.
- If `requests` is not installed, the script falls back to urllib.
- Keep your credentials secure and consider using an API token if available.

## Downloads

Pre-built RPMs and source archives are available in the `dist/` directory of this repository:

- [dist/zoneedit-ddclient-rpms.zip](dist/zoneedit-ddclient-rpms.zip)
- [dist/noarch/zoneedit-ddclient-1.0-1.noarch.rpm](dist/noarch/zoneedit-ddclient-1.0-1.noarch.rpm)

(See the **Install via RPM** section above for installation commands and post-install steps.)

Repository mirroring

A Gitea workflow is included at `.gitea/workflows/mirror-to-github.yml` that will push changes to **https://github.com/ftsiadimos/zoneedit-ddclient.git** on every push to `main`/`master`.

To enable the workflow, add a repository secret named `GITHUB_PAT` in your Gitea repo settings containing a GitHub Personal Access Token with `repo` (or `public_repo` for public repositories) scope so the action can authenticate and push.

---

Install from Git (build or run in-place)

If you prefer to install and configure from a Git clone:

1. Clone the repository and change into it:
   ```bash
   git clone <repo-url>
   cd ZoneEdit-ddclient
   ```

2a. Quick test without installing (run directly):
   ```bash
   python3 zoneedit_ddclient.py --config zoneedit_ddclient.ini.example --once
   ```

2b. To build and install an RPM locally (recommended for system integration):
   ```bash
   make rpm
   sudo dnf install ./dist/noarch/zoneedit-ddclient-1.0-1.noarch.rpm
   ```

3. After installing or running, copy and edit `/etc/zoneedit_ddclient.ini` as described above, create the `state_dir` if needed, and enable/start the service with systemd.
