# EVE Nemesis Tracker

A static website showing your EVE Online nemesis — the person who has killed you the most. Also shows who *you* kill the most (who considers you their nemesis). Hosted on GitHub Pages, updated weekly from zKillboard's public history dumps.

## What's New: zKill Static Database

Instead of querying zKill API per-character (slow, rate-limited, can't scale), we now:

1. **Download** zKill's daily history dumps (~12k-18k killmails/day, 94M+ since 2007)
2. **Build** a local SQLite database of all character kill relationships
3. **Compute** nemesis for every character with losses using SQL
4. **Export** JSON for the static site — covering anyone in the database

Result: search any character with 3+ losses and get instant results. No per-character API calls.

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  GitHub     │◄────│  Raspberry  │◄────│  zKillboard │
│  Pages      │     │  Pi (weekly │     │  History    │
│  (static)   │     │   cron job) │     │  Dumps      │
└─────────────┘     └─────────────┘     └─────────────┘
                           │
                           ▼
                    ┌─────────────┐
                    │  SQLite DB  │
                    │ (nemesis.db)│
                    └─────────────┘
```

- **Frontend**: Pure HTML/CSS/JS in `site/`, deployable to GitHub Pages
- **Backend**: `backend/build_nemesis.py` — downloads history, builds SQLite, exports JSON
- **Runner**: `backend/run.sh` — handles init, weekly updates, git push
- **Data**: JSON files in `site/data/` — one per character + index + reverse index

## Quick Start

```bash
cd backend
pip install -r requirements.txt

# First time: build database and export
bash run.sh init

# Or start from recent history only (faster)
bash run.sh init 20240101

# Weekly update (adds new days, exports, git push)
bash run.sh weekly
```

See [DEPLOY.md](DEPLOY.md) for GitHub Pages setup and automation.

## Setup

### 1. Frontend (GitHub Pages)

In repo settings, set Pages to deploy from `/site` folder on main branch.

### 2. Backend (Raspberry Pi / any Linux box)

```bash
cd backend
pip install -r requirements.txt

# Full build (all history since 2007 — takes hours)
bash run.sh init

# Partial build (from 2024-01-01 — much faster)
bash run.sh init 20240101

# Weekly update + export + git push
bash run.sh weekly
```

### Commands

```bash
bash run.sh init [START_DATE]    # Build database. Optional YYYYMMDD start.
bash run.sh backfill END_DATE   # Import history up to END_DATE (expand backward).
bash run.sh weekly              # Update DB, export JSON, git commit+push
bash run.sh export              # Export only (no DB update)
bash run.sh stats               # Show database statistics
bash run.sh help                # Full help
```

### Environment Variables

```bash
NEMESIS_DB=./nemesis.db           # SQLite database path
NEMESIS_OUTPUT=../site/data       # JSON export directory
NEMESIS_MIN_LOSSES=3              # Min losses to include a character
PYTHON=python3                    # Python executable
```

Example with overrides:
```bash
NEMESIS_DB=/mnt/usb/nemesis.db NEMESIS_MIN_LOSSES=5 bash run.sh weekly
```

### Partial Build + Backfill

Start from 2026 for quick results, then fill in history later:

```bash
# Start from 2026 (minutes instead of hours)
bash run.sh init 20260101

# Weekly updates
bash run.sh weekly

# Eventually, backfill everything before 2026
bash run.sh backfill 20251231
```

### Database Size

| Metric | Estimate |
|--------|----------|
| Total killmails (2007-2025) | ~94M |
| Character-only kills | ~60-70M |
| SQLite DB size | ~8-15GB |
| Export JSON (min 3 losses) | ~500k-1M characters |
| Daily increment | ~15k kills, ~10MB |

### 3. USB Stick Mode

```bash
export NEMESIS_DB=/mnt/usb/nemesis.db
export NEMESIS_OUTPUT=/mnt/usb/nemesis-data

bash run.sh init
bash run.sh weekly

# Serve locally
python -m http.server 8000 --directory /mnt/usb/nemesis-data/
```

## Scheduling

### Cron (weekly, Monday 3am)

```bash
crontab -e
```

Add:
```cron
0 3 * * 1 cd /path/to/nemesis/backend && bash run.sh weekly >> /path/to/nemesis/cron.log 2>&1
```

### systemd Timer (Linux)

Create `/etc/systemd/system/nemesis.service`:
```ini
[Unit]
Description=EVE Nemesis Tracker Weekly Update
After=network.target

[Service]
Type=oneshot
WorkingDirectory=/path/to/nemesis/backend
ExecStart=bash /path/to/nemesis/backend/run.sh weekly
User=pi
```

Create `/etc/systemd/system/nemesis.timer`:
```ini
[Unit]
Description=Run Nemesis Tracker weekly

[Timer]
OnCalendar=Mon *-*-* 03:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

Enable:
```bash
sudo systemctl daemon-reload
sudo systemctl enable nemesis.timer
sudo systemctl start nemesis.timer
sudo systemctl list-timers --all
```

### Windows Task Scheduler

1. Open Task Scheduler → Create Basic Task
2. Name: `Nemesis Tracker Weekly`
3. Trigger: Weekly, Monday, 3:00 AM
4. Action: Start a program
5. Program: `C:\path\to\python.exe`
6. Arguments: `build_nemesis.py --full ../site/data`
7. Start in: `C:\path\to\nemesis\backend`

### macOS launchd

Create `~/Library/LaunchAgents/com.nemesis.tracker.plist`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.nemesis.tracker</string>
  <key>ProgramArguments</key>
  <array>
    <string>bash</string>
    <string>/path/to/nemesis/backend/run.sh</string>
    <string>weekly</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Weekday</key><integer>1</integer>
    <key>Hour</key><integer>3</integer>
    <key>Minute</key><integer>0</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>/path/to/nemesis/cron.log</string>
  <key>StandardErrorPath</key>
  <string>/path/to/nemesis/cron.log</string>
</dict>
</plist>
```

Load:
```bash
launchctl load ~/Library/LaunchAgents/com.nemesis.tracker.plist
launchctl start com.nemesis.tracker
```

## Usage

1. Build the database (one-time, takes a few hours for full history)
2. Set up weekly scheduling (cron, systemd, etc.)
3. The frontend auto-updates when new JSON is pushed to GitHub
4. Search any character with 3+ recorded losses

## Reverse Nemesis

The site shows two directions:
- **Your Nemesis**: Who kills *you* the most
- **You Are Their Nemesis**: Who *you* kill the most — characters for whom YOU are their nemesis

This is computed from the full killmail database, so it's complete for all tracked characters.

## Data Sources

- **zKillboard History API**: Daily JSON dumps at `https://r2z2.zkillboard.com/history/raw/YYYYMMDD.json`
- **ESI (EVE Swagger Interface)**: Character/ship name resolution via `/universe/names/`

No API keys needed — all public data.
