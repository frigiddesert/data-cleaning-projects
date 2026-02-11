# Outline → D1 Sync Worker

Automatically syncs tour data from Outline (human-friendly CMS) to Cloudflare D1 (structured database for website queries).

## Overview

**Worker URL:** https://outline-d1-sync.eric-c5f.workers.dev
**D1 Database:** `rim-tours-db` (1875a129-913d-4799-bf51-66b3e7195808)
**Sync Frequency:** Every hour via GitHub Actions

## Architecture

```
Outline (edit tours)
    ↓ (GitHub Actions triggers hourly)
Cloudflare Worker (polls for changes)
    ↓ (parse markdown → structured data)
D1 Database (tours, images, marketing copy)
    ↓ (website queries)
Website (fast, structured data access)
```

## API Endpoints

- `GET /api/tours` - List all tours with optional filters
- `GET /api/tours/:code` - Single tour details
- `GET /api/sync-status` - Sync statistics
- `POST /api/sync-now` - Manual trigger (admin)

See `/D1_API_DOCUMENTATION.md` for complete API docs.

## Data Flow

1. **GitHub Actions** runs hourly at :15 past the hour
2. **Worker** polls Outline API for changed documents
3. **Parser** extracts structured data from markdown
4. **D1** stores updated tour data
5. **Website** queries D1 for fast, structured access

## What Gets Synced

**FROM Outline:**
- Tour name, code, description
- Tour details (type, difficulty, duration, region, season)
- Content (meeting info, itinerary, what to bring)
- Marketing copy variations
- Metadata (Outline ID, WordPress URL, Arctic ID)

**NOT Synced (fetched live):**
- Arctic availability data (website queries Arctic API directly)
- Pricing (website queries Arctic API directly)

## Development

### Deploy

```bash
npm install
npx wrangler deploy
```

### Set Secrets

```bash
echo "value" | npx wrangler secret put OUTLINE_API_URL
echo "value" | npx wrangler secret put OUTLINE_API_KEY
echo "value" | npx wrangler secret put OUTLINE_DAY_TOURS_DOC_ID
echo "value" | npx wrangler secret put OUTLINE_MD_TOURS_DOC_ID
```

### Test Locally

```bash
npx wrangler dev
```

### View Logs

```bash
npx wrangler tail outline-d1-sync
```

### Query Database

```bash
npx wrangler d1 execute rim-tours-db --remote --command "SELECT * FROM tours LIMIT 5"
```

## Database Schema

See `schema.sql` for full schema. Key tables:

- `tours` - Core tour information
- `tour_images` - Image references
- `tour_marketing_copy` - Marketing variations
- `sync_metadata` - Sync state tracking

## Manual Sync

Trigger via GitHub Actions:
```bash
gh workflow run "Outline → D1 Sync"
```

Or via curl:
```bash
curl -X POST https://outline-d1-sync.eric-c5f.workers.dev/api/sync-now
```

## Monitoring

- **Sync logs:** GitHub Actions → Outline → D1 Sync workflow
- **Worker logs:** `npx wrangler tail outline-d1-sync`
- **Sync status:** `GET /api/sync-status`

## Troubleshooting

**No tours being synced:**
- Check that tours have changed in Outline since last sync
- Reset sync timestamp: `UPDATE sync_metadata SET value = '1970-01-01T00:00:00Z' WHERE key = 'last_sync'`

**Parser errors:**
- Check Outline document format matches expected structure (see `src/parser.ts`)
- Tour title must match: `CODE - Name` format

**Deployment fails:**
- Ensure secrets are set correctly
- Check wrangler.toml has correct database_id
- Verify D1 database exists: `npx wrangler d1 list`

## Files

- `src/index.ts` - Worker entry point, cron handler, API endpoints
- `src/parser.ts` - Outline markdown parser
- `src/types.ts` - TypeScript interfaces
- `schema.sql` - D1 database schema
- `wrangler.toml` - Worker configuration
- `package.json` - Dependencies

## Related Files

- `.github/workflows/outline-d1-sync.yml` - GitHub Actions workflow
- `/D1_API_DOCUMENTATION.md` - Complete API documentation for website
- `/sync_arctic_availability.py` - Arctic availability sync (separate process)

---

**Last Updated:** 2026-02-11
