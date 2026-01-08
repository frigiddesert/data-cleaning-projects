# RimTours Website Schema

This document describes the PostgreSQL database schema for tour data. Use this to build tour template pages.

## Database Connection

```
Host: (your production host)
Port: 5433
Database: rimtours
```

---

## Website Categories

Tours are categorized for the public website. Map `tour_type` values to these display categories:

| Website Category | `tour_type` Contains |
|-----------------|---------------------|
| **Day Tours** | `Day Tours` (not containing `eBike`) |
| **E-Bike Tours** | `eBike` |
| **Multi-Day Camping Tours** | `Multi-Day Tours` (not containing `Private`) |
| **Private & Custom Tours** | `Private` |

### Query Examples

```sql
-- Day Tours (non-ebike)
SELECT * FROM tours
WHERE tour_type LIKE 'Day Tours%'
  AND tour_type NOT LIKE '%eBike%';

-- E-Bike Tours (day and multi-day)
SELECT * FROM tours
WHERE tour_type LIKE '%eBike%';

-- Multi-Day Camping Tours
SELECT * FROM tours
WHERE tour_type LIKE 'Multi-Day Tours%'
  AND tour_type NOT LIKE '%Private%';

-- Private & Custom Tours
SELECT * FROM tours
WHERE tour_type LIKE '%Private%';
```

---

## Main Table: `tours`

| Field | Type | Description |
|-------|------|-------------|
| `id` | integer | Primary key |
| `slug` | varchar | URL-safe identifier (e.g., `dead-horse-point-singletrack`) |
| `title` | varchar | Display title |
| `subtitle` | text | Tagline or short hook |
| `short_description` | text | 1-2 sentence summary for cards/listings |
| `description` | text | Full marketing description (may contain markdown) |
| `tour_type` | varchar | Category classification (see above) |
| `duration` | varchar | e.g., "Full Day", "3 Days", "4-5 Hours" |
| `skill_level` | varchar | e.g., "Beginner", "Intermediate", "Advanced" |
| `distance` | varchar | e.g., "15-20 miles" |
| `terrain` | text | Trail/terrain description |
| `altitude` | varchar | Elevation info |
| `technical_difficulty` | text | Technical rating/description |
| `tour_rating` | text | Overall rating info |
| `region` | varchar | Geographic area |
| `season` | varchar | When tour runs |
| `departs` | varchar | Departure location/time |
| `meeting_time` | varchar | Guest meeting time |
| `meeting_location` | text | Where guests meet |
| `scheduled_dates` | text | Available dates (from Arctic) |
| `special_notes` | text | Important guest info |
| `reservation_link` | text | Arctic booking URL |
| `arctic_id` | varchar | Arctic Adventures system ID |
| `arctic_shortname` | varchar | Arctic short code |

---

## Pricing: `tour_pricing`

```sql
SELECT * FROM tour_pricing WHERE tour_id = ?;
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | integer | Primary key |
| `tour_id` | integer | FK to tours |
| `label` | varchar | Price tier name (e.g., "1 Person", "2-3 People") |
| `amount` | decimal | Numeric price |
| `amount_display` | text | Formatted price (e.g., "$299/person") |
| `notes` | text | Price conditions |

---

## Fees: `tour_fees`

```sql
SELECT * FROM tour_fees WHERE tour_id = ?;
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | integer | Primary key |
| `tour_id` | integer | FK to tours |
| `fee_type` | varchar | e.g., "Park Fee", "Shuttle Fee" |
| `amount` | decimal | Fee amount |
| `description` | text | Fee details |

---

## Itinerary: `tour_itinerary_days`

For multi-day tours. Query by day order:

```sql
SELECT * FROM tour_itinerary_days
WHERE tour_id = ?
ORDER BY day_number;
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | integer | Primary key |
| `tour_id` | integer | FK to tours |
| `day_number` | integer | Day 1, 2, 3... |
| `title` | varchar | Day title (e.g., "Arrival & Orientation") |
| `description` | text | Day narrative |
| `miles` | text | Distance for the day |
| `elevation` | text | Elevation gain/loss |
| `trails_waypoints` | text | Trail names or waypoints |
| `camp_lodging` | text | Where guests stay |
| `meals` | text | Meals provided |

---

## Images: `tour_images`

```sql
SELECT * FROM tour_images WHERE tour_id = ? ORDER BY sort_order;
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | integer | Primary key |
| `tour_id` | integer | FK to tours |
| `url` | text | Image URL |
| `alt_text` | varchar | Accessibility text |
| `caption` | text | Display caption |
| `is_featured` | boolean | Hero image flag |
| `sort_order` | integer | Display order |

---

## Tour Page Template Data

A single API call or query to get all tour data:

```sql
-- Main tour
SELECT * FROM tours WHERE slug = 'dead-horse-point-singletrack';

-- Related data (run with tour_id)
SELECT * FROM tour_pricing WHERE tour_id = ?;
SELECT * FROM tour_fees WHERE tour_id = ?;
SELECT * FROM tour_itinerary_days WHERE tour_id = ? ORDER BY day_number;
SELECT * FROM tour_images WHERE tour_id = ? ORDER BY sort_order;
```

---

## Listing Page Query

For category listing pages:

```sql
SELECT
    slug,
    title,
    subtitle,
    short_description,
    duration,
    skill_level,
    (SELECT url FROM tour_images
     WHERE tour_id = tours.id AND is_featured = true
     LIMIT 1) as featured_image,
    (SELECT MIN(amount) FROM tour_pricing
     WHERE tour_id = tours.id) as starting_price
FROM tours
WHERE tour_type LIKE 'Day Tours%'
ORDER BY title;
```

---

## Data Sources

| Data | Source | Sync Frequency |
|------|--------|----------------|
| Pricing, Dates | Arctic Adventures API | On-demand |
| Descriptions, Itineraries | Outline (staff-editable) | On-demand |
| Classification, Slugs | PostgreSQL (source of truth) | -- |

---

## Notes

- All text fields may contain markdown formatting
- `scheduled_dates` comes from Arctic and shows available booking dates
- `reservation_link` points to Arctic Adventures booking system
- Images are stored as URLs (not uploaded to this database)
