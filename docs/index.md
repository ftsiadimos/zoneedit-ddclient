<h1 style="color:#2a9d8f;">ZoneEdit DDClient Updater</h1>

<p><strong style="color:#264653; font-size:1.1em;">A lightweight Python updater for ZoneEdit DNS A records that keeps your public IPv4 address in sync automatically.</strong></p>

## Why Use This Tool?

- <span style="color:#e76f51;">Reliable</span> automatic ZoneEdit A record updates
- <span style="color:#2a9d8f;">Flexible</span> one-shot or long-running `systemd` daemon mode
- <span style="color:#f4a261;">Configurable</span> source IP detection via network interface or external service
- <span style="color:#2a9d8f;">Safe</span> dry-run mode plus per-host state tracking

## Overview

This updater is designed for minimal setup and robust operation. It can:

- keep one or more ZoneEdit-hosted A records current
- run once for manual checks or run continuously as a `systemd` service
- detect your current IPv4 address from a local interface or an external provider
- preserve state across runs so updates happen only when needed

## Quick Start

1. Copy the example config:
   ```bash
   sudo cp /etc/zoneedit_ddclient.ini.example /etc/zoneedit_ddclient.ini
   sudo nano /etc/zoneedit_ddclient.ini
   ```
2. Set `hostnames`, `username`, and `password` in `/etc/zoneedit_ddclient.ini`.
3. Test a single update:
   ```bash
   python3 zoneedit_ddclient.py --config /etc/zoneedit_ddclient.ini --once
   ```
4. Install and enable the `systemd` service:
   ```bash
   sudo cp zoneedit-ddclient.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now zoneedit-ddclient.service
   ```

## Tips

- Use `--dry-run` to verify actions without making changes.
- Keep `/var/lib/zoneedit-ddclient/` writable for state files.
- If you use multiple hosts, configure each under `hostnames` and manage state independently.
