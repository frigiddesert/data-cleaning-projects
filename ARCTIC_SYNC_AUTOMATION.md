# Arctic Sync Automation

## Overview

Arctic availability data is automatically synced to Outline tour documents **daily at 6 AM UTC** using GitHub Actions + Cloudflare Worker.

## Architecture

```
GitHub Actions (Scheduler)
    ↓ (HTTP GET daily at 6 AM)
Cloudflare Worker (arctic-sync)
    ↓
    ├─→ Outline API (fetch tour documents)
    ├─→ Arctic API (fetch availability)
    └─→ Outline API (update documents with latest data)
```

## Components

### 1. GitHub Actions Workflow

**File:** `.github/workflows/arctic-sync.yml`

**Schedule:** Daily at 6:00 AM UTC (11 PM MST / 12 AM MDT)

**What it does:**
- Triggers the Cloudflare Worker via HTTP GET request
- Parses the JSON response
- Checks for failures
- Uploads results as artifacts (kept for 30 days)
- Fails the workflow if any tours fail to sync (sends notification)

**Manual trigger:**
1. Go to https://github.com/your-username/data-cleaning-projects/actions
2. Click "Arctic Sync Daily" workflow
3. Click "Run workflow" button

### 2. Cloudflare Worker

**URL:** https://arctic-sync.eric-c5f.workers.dev

**Endpoints:**
- `GET /` - Worker info
- `GET /sync` - Trigger sync manually (returns JSON)

**What it does:**
- Fetches tour documents from Outline (Day Tours + Multi-Day Tours folders)
- For each tour:
  - Extracts Arctic ID from Reference table
  - Fetches schedule & pricing from Arctic API
  - Updates Outline document with:
    - Latest availability table
    - "Last synced" timestamp
- Returns summary: `{ updated, failed, skipped, results }`

**Code:** `workers/arctic-sync/src/index.ts`

## How to Monitor

### View GitHub Actions Logs

1. Go to: https://github.com/your-username/data-cleaning-projects/actions
2. Click on latest "Arctic Sync Daily" run
3. View logs and download sync results JSON

### View Cloudflare Worker Logs

```bash
cd workers/arctic-sync
npx wrangler tail
```

Or in Cloudflare Dashboard:
- Workers & Pages → arctic-sync → Logs

### Check Outline Documents

Look at any tour document's "Last Updated" section (bottom):

```markdown
## Last Updated

- **Marketing Copy**: 2026-02-10 16:02:58
- **Arctic Availability**: 2026-02-10 06:00:15  ← Should update daily
```

## Troubleshooting

### Workflow fails

**Check:**
1. GitHub Actions logs (link above)
2. Cloudflare Worker logs: `cd workers/arctic-sync && npx wrangler tail`
3. Worker secrets: `cd workers/arctic-sync && npx wrangler secret list`

**Common issues:**
- Worker secrets expired (Outline API key rotated)
- Arctic API authentication changed
- Outline API rate limit exceeded

### Manual sync

**Option 1: GitHub Actions UI**
1. Go to Actions tab → Arctic Sync Daily → Run workflow

**Option 2: Direct HTTP**
```bash
curl "https://arctic-sync.eric-c5f.workers.dev/sync" | jq '.'
```

**Option 3: Local Python script (fallback)**
```bash
cd /home/eric/code/data-cleaning-projects
source .venv/bin/activate
python3 sync_arctic_availability.py
```

## Updating the Worker

If you need to modify the worker logic:

```bash
cd workers/arctic-sync

# Edit src/index.ts
nano src/index.ts

# Deploy changes
npx wrangler deploy

# Test
curl "https://arctic-sync.eric-c5f.workers.dev/sync"
```

## Updating Secrets

If API keys change:

```bash
cd workers/arctic-sync

# Update Outline API key
echo "new_key_here" | npx wrangler secret put OUTLINE_API_KEY

# Update Arctic password
echo "new_password" | npx wrangler secret put ARCTIC_PASSWORD

# List all secrets
npx wrangler secret list
```

## Costs

- **GitHub Actions**: FREE (2,000 minutes/month on free tier)
- **Cloudflare Worker**: FREE (stays within 100k requests/day limit)
- **Total**: $0/month

## Disabling Auto-Sync

To temporarily disable automatic sync:

1. Go to: https://github.com/your-username/data-cleaning-projects/settings/actions
2. Disable "Allow all actions"

Or delete the workflow file:
```bash
rm .github/workflows/arctic-sync.yml
git commit -m "Disable Arctic sync"
git push
```

## Current Status

- ✅ GitHub Actions workflow configured (daily at 6 AM UTC)
- ✅ Cloudflare Worker deployed (arctic-sync.eric-c5f.workers.dev)
- ✅ Worker secrets configured (Outline + Arctic APIs)
- ✅ Manual trigger available via GitHub UI
- ⚠️ Worker currently limited to 12 tours for testing (see note below)

### Note: Worker Tour Limit

The worker is currently limited to processing 12 tours (10 day tours + 2 multi-day) to stay within Cloudflare's 50 subrequest limit on the free tier.

**To process all 58 tours**, you have two options:

1. **Split into multiple workers** (e.g., day-tours-sync, multi-day-sync)
2. **Upgrade to Workers Paid** ($5/month, 50ms CPU time allows more subrequests)
3. **Keep using local Python script** for full syncs (works perfectly)

## Files Reference

- **Workflow:** `.github/workflows/arctic-sync.yml`
- **Worker code:** `workers/arctic-sync/src/index.ts`
- **Worker config:** `workers/arctic-sync/wrangler.toml`
- **Python fallback:** `sync_arctic_availability.py`
- **Local cron:** `run_arctic_sync.sh` (also runs daily at 6 AM as backup)

## Migration from Local Cron

The local cron job (`/home/eric/code/data-cleaning-projects/run_arctic_sync.sh`) is still configured as a backup. You can disable it:

```bash
crontab -e
# Comment out or remove the arctic sync line
```

Or keep both for redundancy! 🛡️
