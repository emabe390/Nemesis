# Deployment Guide

## GitHub Pages (Recommended)

### 1. Push repo to GitHub

```bash
cd ~/nemesis
git init  # if not already
git add .
git commit -m "initial"
git remote add origin https://github.com/YOURNAME/nemesis.git
git push -u origin master
```

### 2. Enable GitHub Pages

- Go to repo Settings → Pages
- Source: Deploy from a branch
- Branch: `master`, folder: `/docs`

### 3. Generate data

```bash
cd ~/nemesis/backend
bash run.sh init 20260101
```

This creates `site/data/` with JSON files.

### 4. Push data to GitHub

```bash
cd ~/nemesis
git add docs/data
git commit -m "nemesis data"
git push
```

### 5. Automate weekly updates

Cron:
```bash
crontab -e
```

Add:
```cron
0 3 * * 1 cd ~/nemesis/backend && NEMESIS_OUTPUT=../docs/data bash run.sh weekly >> ~/nemesis/cron.log 2>&1
```

The `weekly` command updates DB, exports JSON, commits and pushes.

### 6. Access site

`https://YOURNAME.github.io/nemesis/`

---

## Self-Hosted (Raspberry Pi / Linux)

```bash
cd ~/nemesis/site
python3 -m http.server 8000
```

Or use nginx, caddy, etc.

---

## Check current git remote

```bash
cd ~/nemesis
git remote -v
```

If empty, add remote and push. If already set, just push after generating data.
