# Session State — EVE Nemesis Tracker

## Current Project State

### Files
- `backend/build_nemesis.py` — zKill history dump downloader, SQLite builder, nemesis calculator, JSON exporter
- `backend/run.sh` — init / weekly / export / stats / backfill commands
- `backend/requirements.txt` — requests>=2.28.0
- `docs/` — static site (was `site/`, renamed for GitHub Pages `/docs` support)
  - `docs/index.html`, `docs/app.js`, `docs/style.css`, `docs/data/index.json`
- `DEPLOY.md` — deployment instructions
- `README.md` — project docs
- `.gitignore` — ignores README.md and .pi/
- `docs/.nojekyll` — disables Jekyll on GitHub Pages

### Architecture
- Downloads zKill daily history dumps (`r2z2.zkillboard.com/history/raw/YYYYMMDD.json`)
- Builds SQLite DB of all character kill relationships
- Computes nemesis for every character with ≥3 losses via SQL
- Exports JSON for static site (one file per character + index + reverse index)
- Frontend: pure HTML/CSS/JS, queries pre-built JSON

### Key Commands
```bash
cd ~/nemesis/backend
bash run.sh init [YYYYMMDD]      # first build
bash run.sh backfill YYYYMMDD    # expand history backward
bash run.sh weekly               # update + export + git push
bash run.sh export               # export only
bash run.sh stats                # DB stats
```

### GitHub Pages Setup
- Branch: `master`
- Folder: `/docs`
- URL: `https://emabe390.github.io/Nemesis/`
- `.nojekyll` present to disable Jekyll

### Environment
- User: `aitesh`
- Repo: `emabe390/Nemesis` on GitHub
- Raspberry Pi with SD card (ext4) + USB drive (FAT32, not used for DB)
- Backend should run from `~/nemesis/` (home directory, ext4)

### Known Issues / TODO
- Frontend `app.js` references `./data/` path — correct for docs/
- Data not yet generated (no `docs/data/*.json` files pushed)
- Weekly cron not yet set up
- Ship name resolution uses ESI `/universe/names/` with `inventory_type` filter

### Last Actions
- Renamed `site/` → `docs/` for GitHub Pages
- Fixed `run.sh` output path to `../docs/data`
- Added `DEPLOY.md`
- Added `.nojekyll`
- Pushed all to `master`
