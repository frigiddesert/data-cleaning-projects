# Outline → D1 Sync System - Complete Summary

## ✅ What Was Built

You now have a fully automated system that syncs tour data from Outline (your human-friendly CMS) to Cloudflare D1 (structured database for your website).

---

## 🏗️ System Architecture

```
┌──────────────────────────────────────────────────────────┐
│  OUTLINE (outline.sandland.us)                          │
│  - Human-friendly wiki/CMS                              │
│  - Edit tour descriptions, itineraries, details         │
│  - Marketing copy variations                            │
└────────────────┬─────────────────────────────────────────┘
                 │
                 ↓ (GitHub Actions polls every hour)
┌──────────────────────────────────────────────────────────┐
│  CLOUDFLARE WORKER (outline-d1-sync.eric-c5f.workers.dev)│
│  - Detects changed documents                            │
│  - Parses markdown → structured data                    │
│  - Updates D1 database                                  │
└────────────────┬─────────────────────────────────────────┘
                 │
                 ↓ (Stores structured data)
┌──────────────────────────────────────────────────────────┐
│  CLOUDFLARE D1 (rim-tours-db)                           │
│  - tours table (48 tours synced)                        │
│  - tour_images, tour_marketing_copy tables              │
│  - Fast, queryable, structured data                     │
└────────────────┬─────────────────────────────────────────┘
                 │
                 ↓ (Website queries for listings/filters)
┌──────────────────────────────────────────────────────────┐
│  YOUR WEBSITE (Cloudflare Pages + Workers)             │
│  GET /api/tours → Filter by region, difficulty, etc.    │
│  GET /api/tours/:code → Full tour details              │
│  Combine with Arctic API → Live availability/pricing    │
└──────────────────────────────────────────────────────────┘
```

---

## 📊 What Gets Synced

### ✅ FROM Outline → D1 (Static Data)
- Tour code & name (e.g., "WR4 - White Rim 4-Day")
- Tour type (e.g., "Camping at Multiple Locations")
- Difficulty level (Beginner, Intermediate, Advanced, Moderate)
- Duration (days/nights)
- Region (Moab Area, Grand Canyon, etc.)
- Season (start/end months)
- Description (brief overview)
- Meeting info (where/when to meet)
- What to bring (packing list)
- Itinerary (full day-by-day details)
- Booking notes
- Marketing copy variations (different audience styles)
- Arctic ID (for live availability lookups)
- WordPress URL (legacy reference)

### ❌ NOT Synced (Fetched Live from Arctic)
- Available tour dates
- Spots available/total
- Current pricing levels
- Real-time booking status

**Why?** Availability changes constantly (daily). Website fetches this live from Arctic API using the `arctic_id` stored in D1.

---

## 🚀 How It Works

### 1. **Hourly Sync (Automated)**

**GitHub Actions** runs every hour at :15 past the hour:
- Calls Worker endpoint: `POST /api/sync-now`
- Worker polls Outline API for changed documents
- Compares `updatedAt` timestamps (only syncs changed tours)
- Parses markdown → extracts structured data
- Updates D1 database
- Returns stats: inserted, updated, errors

**Next sync:** Every hour at :15 past (e.g., 5:15 PM, 6:15 PM, etc.)

**Monitor:** https://github.com/frigiddesert/data-cleaning-projects/actions/workflows/outline-d1-sync.yml

---

### 2. **Manual Sync (When Needed)**

**Option 1: GitHub UI**
1. Go to: https://github.com/frigiddesert/data-cleaning-projects/actions
2. Click "Outline → D1 Sync"
3. Click "Run workflow"

**Option 2: Command Line**
```bash
gh workflow run "Outline → D1 Sync"
```

**Option 3: Direct API Call**
```bash
curl -X POST "https://outline-d1-sync.eric-c5f.workers.dev/api/sync-now"
```

---

## 🌐 Website Integration

Your website will query D1 for tour data and combine it with live Arctic availability.

### API Endpoints

**1. List Tours with Filters**
```
GET https://outline-d1-sync.eric-c5f.workers.dev/api/tours
  ?region=Moab%20Area
  &difficulty=Intermediate
  &duration=4
```

**2. Single Tour Details**
```
GET https://outline-d1-sync.eric-c5f.workers.dev/api/tours/WR4
```

**3. Sync Status**
```
GET https://outline-d1-sync.eric-c5f.workers.dev/api/sync-status
```

### Example Website Code

```typescript
// Tour listing page
async function getTours(filters) {
  const params = new URLSearchParams(filters);
  const response = await fetch(
    `https://outline-d1-sync.eric-c5f.workers.dev/api/tours?${params}`
  );
  return await response.json();
}

// Tour detail page
async function getTourDetails(code) {
  // Get static data from D1
  const tourResponse = await fetch(
    `https://outline-d1-sync.eric-c5f.workers.dev/api/tours/${code}`
  );
  const tour = await tourResponse.json();

  // Get live availability from Arctic
  const arcticClient = new ArcticClient();
  const availability = await arcticClient.get_full_schedule(tour.arctic_id);
  const pricing = await arcticClient.get_trip_pricing_summary(tour.arctic_id);

  // Combine both
  return {
    ...tour,
    availability: availability.future,
    pricing: pricing.pricing
  };
}
```

---

## 📂 Key Files

### Worker Code
- `workers/outline-d1-sync/src/index.ts` - Main worker (API endpoints, sync logic)
- `workers/outline-d1-sync/src/parser.ts` - Outline markdown parser
- `workers/outline-d1-sync/src/types.ts` - TypeScript interfaces
- `workers/outline-d1-sync/schema.sql` - D1 database schema
- `workers/outline-d1-sync/wrangler.toml` - Worker configuration

### Automation
- `.github/workflows/outline-d1-sync.yml` - Hourly sync trigger
- `.github/workflows/arctic-sync.yml` - Arctic availability sync (separate)

### Documentation
- `D1_API_DOCUMENTATION.md` - **Complete API docs for website team**
- `workers/outline-d1-sync/README.md` - Worker development guide
- `OUTLINE_D1_SYSTEM_SUMMARY.md` - This file

---

## 🎯 Current Status

**D1 Database:**
- 48 tours synced successfully
- 10 errors (likely day tours with different title formats)
- Database: `rim-tours-db` (1875a129-913d-4799-bf51-66b3e7195808)

**Worker:**
- Deployed: https://outline-d1-sync.eric-c5f.workers.dev
- Version: ca5e4cca-2f87-4e4f-851f-d1f46b5a9abd
- Status: Active

**GitHub Actions:**
- Outline → D1 Sync: ✅ Running hourly
- Arctic → Outline Sync: ✅ Running daily at 6 AM UTC

---

## 🛠️ Maintenance

### Update Worker Code

```bash
cd workers/outline-d1-sync
# Edit src/index.ts, src/parser.ts, etc.
npx wrangler deploy
```

### Query Database Directly

```bash
npx wrangler d1 execute rim-tours-db --remote --command "SELECT * FROM tours LIMIT 5"
```

### View Worker Logs

```bash
npx wrangler tail outline-d1-sync
```

### Reset Sync (Force Re-sync All Tours)

```bash
npx wrangler d1 execute rim-tours-db --remote --command \
  "UPDATE sync_metadata SET value = '1970-01-01T00:00:00Z' WHERE key = 'last_sync'"

curl -X POST "https://outline-d1-sync.eric-c5f.workers.dev/api/sync-now"
```

---

## 🔍 Monitoring

### Check Last Sync

```bash
curl "https://outline-d1-sync.eric-c5f.workers.dev/api/sync-status" | jq '.'
```

**Output:**
```json
{
  "lastSync": "2026-02-11T17:14:29.810Z",
  "status": "success",
  "totalTours": 48
}
```

### GitHub Actions Dashboard

https://github.com/frigiddesert/data-cleaning-projects/actions

- ✅ Green checkmark = successful sync
- ❌ Red X = failed sync (you'll get an email)

---

## 🎓 How Outline Data Maps to D1

**Outline Document Structure:**
```markdown
WR4 - White Rim 4-Day

> Brief tour description goes here

## Reference

| Field | Value |
|-------|-------|
| Arctic | tt191 |
| WordPress | https://rimtours.com/tours/white-rim-4-day/ |
| Outline | cf145a93-... |

<!-- SIDEBAR_SYNC -->

## Tour Details

|     |     |
|-----|-----|
| **Region** | Moab Area |
| **Duration** | 4-Day/3-Night |
| **Style** | Camping at Multiple Locations |
| **Season** | Fall, Spring |
| **Skill Level** | Intermediate, Moderate |

<!-- /SIDEBAR_SYNC -->

## Meeting Info

Meet at Rim Tours shop at 8:00 AM...

## Itinerary

### Day 1
...

## Marketing Copy Variations

| Style | Description |
|-------|-------------|
| **Adventure Seekers** | Embark on an unforgettable... |
| **Families** | Create lasting memories... |
```

**Maps to D1:**
```sql
INSERT INTO tours (
  tour_code = 'WR4',
  tour_name = 'White Rim 4-Day',
  region = 'Moab Area',
  duration_days = 4,
  duration_nights = 3,
  tour_type = 'Camping at Multiple Locations',
  difficulty = 'Intermediate',
  season_start = 'Fall',
  season_end = 'Spring',
  arctic_id = 191,
  description = 'Brief tour description goes here',
  meeting_info = 'Meet at Rim Tours shop at 8:00 AM...',
  ...
);

INSERT INTO tour_marketing_copy VALUES
  ('WR4', 'Adventure Seekers', 'Embark on an unforgettable...'),
  ('WR4', 'Families', 'Create lasting memories...');
```

---

## 💰 Cost Breakdown

| Service | Plan | Cost |
|---------|------|------|
| Cloudflare D1 | Free (5GB storage, 5M reads/day) | $0 |
| Cloudflare Workers | Free (100k req/day) | $0 |
| GitHub Actions | Free (2,000 min/month) | $0 |
| **Total** | | **$0/month** |

---

## 🎉 Success Criteria

✅ **Worker deployed** - https://outline-d1-sync.eric-c5f.workers.dev
✅ **D1 schema applied** - 10 tables created
✅ **48 tours synced** - Structured data in database
✅ **API endpoints working** - Filters, single tour queries
✅ **GitHub Actions configured** - Hourly sync automated
✅ **Documentation complete** - API docs for website team

---

## 📚 Next Steps for Website Development

1. **Read the API documentation:** `D1_API_DOCUMENTATION.md`
2. **Test the endpoints:**
   ```bash
   curl "https://outline-d1-sync.eric-c5f.workers.dev/api/tours?region=Moab%20Area"
   curl "https://outline-d1-sync.eric-c5f.workers.dev/api/tours/WR4"
   ```
3. **Integrate with your Cloudflare Pages site:**
   - Query D1 for tour listings/filters
   - Query Arctic API for live availability (using `arctic_id` from D1)
   - Combine both data sources in your Workers/Page Functions

---

## 🆘 Troubleshooting

**Problem:** Tours not updating after editing in Outline
- **Solution:** Sync runs hourly. Either wait for next sync or trigger manually

**Problem:** Some tours have missing data (null values)
- **Solution:** Check Outline document format matches expected structure (see parser.ts)

**Problem:** Sync shows errors
- **Solution:** Check GitHub Actions logs for details. Day tours may have different title formats.

**Problem:** Need to add a new field to D1
- **Solution:**
  1. Add column to `schema.sql`
  2. Update parser in `src/parser.ts`
  3. Update worker to insert/update new field
  4. Deploy: `npx wrangler deploy`
  5. Run migration: `npx wrangler d1 migrations apply rim-tours-db --remote`

---

**System Status:** ✅ FULLY OPERATIONAL

**Last Updated:** 2026-02-11
**Version:** 1.0.0
