# Rim Tours D1 API Documentation

## Overview

Tour data is automatically synced from Outline to Cloudflare D1 and exposed via Worker API endpoints. Your website queries D1 for static tour information and queries Arctic API directly for live availability/pricing.

**Worker URL:** `https://outline-d1-sync.eric-c5f.workers.dev`

---

## Architecture

```
┌───────────────────┐
│  OUTLINE          │  Human-friendly CMS (edit tours here)
│  (Source of Truth)│
└─────────┬─────────┘
          │
          ↓ (Synced via GitHub Actions every hour)
┌───────────────────┐
│  CLOUDFLARE D1    │  Structured tour database
│  (rim-tours-db)   │  - tours, tour_images, tour_marketing_copy
└─────────┬─────────┘
          │
          ↓ (Your website queries)
┌───────────────────┐
│  WEBSITE          │  Cloudflare Pages + Workers
│  GET /api/tours   │  - List tours with filters
│  GET /api/tours/  │  - Single tour details
│      :code        │  - Live Arctic availability
└───────────────────┘
```

---

## API Endpoints

### 1. **List All Tours** (with optional filters)

```
GET https://outline-d1-sync.eric-c5f.workers.dev/api/tours
```

**Query Parameters:**
- `type` - Filter by tour type (e.g., `Camping at Multiple Locations`)
- `difficulty` - Filter by skill level (e.g., `Intermediate`, `Moderate`, `Beginner`)
- `region` - Filter by region (e.g., `Moab Area`, `Grand Canyon`, `Crested Butte`)
- `duration` - Filter by number of days (e.g., `4`, `5`, `1`)

**Response:**
```json
{
  "tours": [
    {
      "tour_code": "WR4",
      "tour_name": "White Rim 4-Day",
      "tour_type": "Camping at Multiple Locations",
      "difficulty": "Intermediate",
      "duration_days": 4,
      "duration_nights": 3,
      "region": "Moab Area",
      "season_start": "Fall",
      "season_end": "Spring",
      "arctic_id": 191,
      "description": "Four days of epic singletrack riding...",
      "price_range": "$1000-2000",
      "has_ebike": 1,
      "is_private": 0,
      "outline_id": "cf145a93-...",
      "outline_updated_at": "2026-02-11T...",
      "synced_at": "2026-02-11T..."
    }
  ]
}
```

**Example Requests:**
```bash
# All tours
curl "https://outline-d1-sync.eric-c5f.workers.dev/api/tours"

# Intermediate tours in Moab
curl "https://outline-d1-sync.eric-c5f.workers.dev/api/tours?region=Moab%20Area&difficulty=Intermediate"

# Multi-day camping tours
curl "https://outline-d1-sync.eric-c5f.workers.dev/api/tours?type=Camping%20at%20Multiple%20Locations"

# 4-day tours
curl "https://outline-d1-sync.eric-c5f.workers.dev/api/tours?duration=4"
```

---

### 2. **Get Single Tour Details**

```
GET https://outline-d1-sync.eric-c5f.workers.dev/api/tours/:tourCode
```

**Response:**
```json
{
  "tour_code": "WR4",
  "tour_name": "White Rim 4-Day",
  "tour_type": "Camping at Multiple Locations",
  "difficulty": "Intermediate",
  "duration_days": 4,
  "duration_nights": 3,
  "region": "Moab Area",
  "season_start": "Fall",
  "season_end": "Spring",
  "arctic_id": 191,
  "description": "Four days of epic singletrack...",
  "meeting_info": "Meet at Rim Tours shop at 8:00 AM...",
  "what_to_bring": "Riding clothes, sunscreen...",
  "itinerary_overview": "## Day 1\n\nWe'll start by...",
  "booking_notes": "Book at least 7 days in advance...",
  "wordpress_url": "https://rimtours.com/tours/white-rim-4-day/",
  "outline_id": "cf145a93-...",
  "price_range": "$1000-2000",
  "has_ebike": 1,
  "is_private": 0,
  "marketingCopy": [
    {
      "style": "Adventure Seekers",
      "description": "Embark on an unforgettable 4-day journey..."
    },
    {
      "style": "Families",
      "description": "Create lasting memories with your family..."
    }
  ]
}
```

**Example:**
```bash
curl "https://outline-d1-sync.eric-c5f.workers.dev/api/tours/WR4"
```

---

### 3. **Get Sync Status**

```
GET https://outline-d1-sync.eric-c5f.workers.dev/api/sync-status
```

**Response:**
```json
{
  "lastSync": "2026-02-11T17:14:29.810Z",
  "status": "success",
  "totalTours": 48
}
```

---

### 4. **Manual Sync Trigger** (Admin only)

```
POST https://outline-d1-sync.eric-c5f.workers.dev/api/sync-now
```

**Response:**
```json
{
  "success": true,
  "stats": {
    "totalProcessed": 58,
    "inserted": 0,
    "updated": 48,
    "errors": 10,
    "lastSync": "2026-02-11T17:14:29.810Z"
  }
}
```

---

## Live Availability Data (Arctic API)

**IMPORTANT:** Availability and current pricing data is NOT stored in D1. Your website must fetch this live from Arctic API using the `arctic_id` field.

### Get Live Availability

Use the existing Arctic API client in this repo:

```typescript
// In your Cloudflare Worker/Page Function
import { ArcticClient } from './arctic_client';

const arctic = new ArcticClient();

// Get tour from D1
const tour = await getTourFromD1('WR4');

// Fetch live availability using arctic_id
const availability = await arctic.get_full_schedule(tour.arctic_id);
const pricing = await arctic.get_trip_pricing_summary(tour.arctic_id);

// Combine D1 static data + Arctic live data
return {
  ...tour,
  availability: {
    upcomingDates: availability.future,
    pricing: pricing.pricing,
    lastUpdated: new Date().toISOString()
  }
};
```

**Arctic API Methods:**
- `get_full_schedule(tripTypeId)` - Returns all scheduled dates with availability
- `get_trip_pricing_summary(tripTypeId)` - Returns pricing levels

See `arctic_client.py` for full API documentation.

---

## D1 Database Schema

### `tours` Table

| Column | Type | Description |
|--------|------|-------------|
| `tour_code` | TEXT | Primary key (e.g., "WR4", "KOKO5") |
| `tour_name` | TEXT | Full tour name |
| `tour_type` | TEXT | Style (e.g., "Camping at Multiple Locations") |
| `difficulty` | TEXT | Skill level (Beginner, Intermediate, Advanced, Moderate) |
| `duration_days` | INTEGER | Number of days |
| `duration_nights` | INTEGER | Number of nights |
| `region` | TEXT | Geographic region |
| `season_start` | TEXT | Start of season (e.g., "Fall", "March") |
| `season_end` | TEXT | End of season (e.g., "Spring", "November") |
| `arctic_id` | INTEGER | Arctic Reservations trip type ID |
| `description` | TEXT | Brief tour description |
| `meeting_info` | TEXT | Where/when to meet |
| `what_to_bring` | TEXT | Packing list |
| `itinerary_overview` | TEXT | Full itinerary markdown |
| `booking_notes` | TEXT | Special booking instructions |
| `wordpress_url` | TEXT | Legacy WordPress URL |
| `outline_id` | TEXT | Outline document ID |
| `price_range` | TEXT | Estimated price range (computed) |
| `has_ebike` | INTEGER | 1 if ebike tour, 0 otherwise |
| `is_private` | INTEGER | 1 if private only, 0 otherwise |
| `is_active` | INTEGER | 1 if active, 0 if archived |
| `outline_updated_at` | TEXT | ISO timestamp from Outline |
| `synced_at` | TEXT | Last sync timestamp |

### `tour_images` Table

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Auto-increment primary key |
| `tour_code` | TEXT | Foreign key to tours.tour_code |
| `image_type` | TEXT | "hero", "gallery", "inline" |
| `image_path` | TEXT | Relative path (e.g., "tours/wr4/hero.jpg") |
| `image_url` | TEXT | Full URL if hosted externally |
| `alt_text` | TEXT | Accessibility text |
| `sort_order` | INTEGER | Display order |

### `tour_marketing_copy` Table

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Auto-increment primary key |
| `tour_code` | TEXT | Foreign key to tours.tour_code |
| `style` | TEXT | Audience (e.g., "Adventure Seekers", "Families") |
| `description` | TEXT | Marketing copy for that audience |

---

## Sync Schedule

**GitHub Actions runs every hour:**
- Polls Outline API for changed documents
- Parses markdown → structured data
- Updates D1 database
- Only syncs tours that have changed since last run

**Manual sync:**
```bash
curl -X POST "https://outline-d1-sync.eric-c5f.workers.dev/api/sync-now"
```

---

## Filter Values (for website UI)

### Regions
Query database for unique values:
```sql
SELECT DISTINCT region FROM tours WHERE is_active = 1 ORDER BY region;
```

**Common values:**
- Moab Area
- Grand Canyon
- Crested Butte
- Colorado, Utah
- Canyonlands
- Durango
- Arizona

### Difficulty Levels
- Beginner
- Intermediate
- Moderate
- Advanced

### Tour Types
- Camping at Multiple Locations
- Half Day
- Full Day
- Bed & Breakfast Inns
- (See full list in database)

### Duration
- 1 (Half/Full day tours)
- 3-6 (Multi-day tours)

---

## CORS Support

All endpoints support CORS with:
```
Access-Control-Allow-Origin: *
Access-Control-Allow-Methods: GET, POST, OPTIONS
```

---

## Error Handling

**404 Not Found:**
```json
{
  "error": "Tour not found"
}
```

**500 Internal Server Error:**
```json
{
  "error": "Internal server error",
  "message": "Detailed error message"
}
```

---

## Example Website Integration

### Tour Listing Page

```typescript
// /tours page
export async function onRequest(context) {
  const { region, difficulty, duration } = context.request.query;

  // Build query string
  const params = new URLSearchParams();
  if (region) params.set('region', region);
  if (difficulty) params.set('difficulty', difficulty);
  if (duration) params.set('duration', duration);

  // Fetch from D1
  const response = await fetch(
    `https://outline-d1-sync.eric-c5f.workers.dev/api/tours?${params}`
  );
  const { tours } = await response.json();

  // Render tour cards
  return new Response(renderTourCards(tours), {
    headers: { 'Content-Type': 'text/html' }
  });
}
```

### Tour Detail Page

```typescript
// /tours/[code] page
export async function onRequest(context) {
  const { code } = context.params;

  // Fetch tour from D1
  const tourResponse = await fetch(
    `https://outline-d1-sync.eric-c5f.workers.dev/api/tours/${code}`
  );
  const tour = await tourResponse.json();

  if (tour.error) {
    return new Response('Tour not found', { status: 404 });
  }

  // Fetch live availability from Arctic
  const arctic = new ArcticClient(context.env);
  const availability = await arctic.get_full_schedule(tour.arctic_id);
  const pricing = await arctic.get_trip_pricing_summary(tour.arctic_id);

  // Combine data
  const pageData = {
    ...tour,
    availability: availability.future,
    pricing: pricing.pricing
  };

  return new Response(renderTourPage(pageData), {
    headers: { 'Content-Type': 'text/html' }
  });
}
```

---

## Support

- **D1 Database:** `rim-tours-db` (1875a129-913d-4799-bf51-66b3e7195808)
- **Worker:** `outline-d1-sync` (https://outline-d1-sync.eric-c5f.workers.dev)
- **Source Code:** `/workers/outline-d1-sync/`
- **Schema:** `/workers/outline-d1-sync/schema.sql`

**Monitoring:**
- Sync logs: Check GitHub Actions runs
- Worker logs: `npx wrangler tail outline-d1-sync`
- Database queries: `npx wrangler d1 execute rim-tours-db --remote --command "SELECT ..."`

---

**Last Updated:** 2026-02-11
**Version:** 1.0.0
