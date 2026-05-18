# ZoneEdit DDClient Updater

ZoneEdit DDClient Updater is a lightweight Python service for keeping ZoneEdit DNS A records synchronized with your current public IPv4 address.

## Overview

- Keeps ZoneEdit-hosted A records up to date
- Supports one-shot updates and a long-lived `systemd` daemon
- Reads IP from a network interface or an external check service
- Includes dry-run mode and per-host state files

## Quick Start

1. Copy the example config:
   ```bash
   sudo cp /etc/zoneedit_ddclient.ini.example /etc/zoneedit_ddclient.ini
   sudo nano /etc/zoneedit_ddclient.ini
   ```
2. Configure `hostnames`, `username`, and `password`.
3. Test a single run:
   ```bash
   python3 zoneedit_ddclient.py --config /etc/zoneedit_ddclient.ini --once
   ```
4. Install and enable the included `systemd` service:
   ```bash
   sudo cp zoneedit-ddclient.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now zoneedit-ddclient.service
   ```

## Documentation

See the repository `README.md` for full installation, configuration, and packaging instructions.

## Project Link

- [ZoneEdit-ddclient project on Docker AgonyWeb](http://docker.agonyweb.com:3000/fotis/ZoneEdit-ddclient)

---

> This page is generated from the repository docs folder and can be published via GitHub Pages.
