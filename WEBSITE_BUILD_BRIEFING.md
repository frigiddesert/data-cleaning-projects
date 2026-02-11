# Website Build Briefing - Rim Tours Website Rebuild

**Last Updated:** 2026-02-11
**For:** AI Agent building the new Rim Tours website
**Project:** Complete website rebuild on Cloudflare Pages

---

## 🎯 Mission

Build a **fast, static website** for Rim Tours (mountain bike tour company) that:
- Loads instantly (static HTML from CDN)
- Shows live tour availability (client-side fetch from Arctic API)
- Displays tour information from structured database (Cloudflare D1)
- Uses images scraped from old WordPress site

---

## 📚 Essential Files to Read (In Order)

### 1. **STATIC_WEBSITE_ARCHITECTURE.md** ⭐ START HERE
**What it is:** Complete architecture guide for building the static site
**Key info:**
- How to fetch D1 data at build time
- Generate static HTML pages
- Client-side JavaScript for live Arctic availability
- Framework examples (Astro, Next.js, plain HTML)
- Security patterns (Arctic proxy Worker)

### 2. **D1_API_DOCUMENTATION.md** ⭐ API REFERENCE
**What it is:** Complete API reference for querying tour data
**Key endpoints:**
- `GET /api/tours` - List all tours with filters
- `GET /api/tours/:code` - Single tour details
- Response formats, query parameters, examples

**Base URL:** `https://outline-d1-sync.eric-c5f.workers.dev`

### 3. **image_manifest.json** ⭐ IMAGE INVENTORY
**What it is:** Complete mapping of WordPress images to tour pages
**Location:** `/home/eric/code/data-cleaning-projects/image_manifest.json`
**Stats:**
- 252 pages cataloged
- 1,485 total image references
- 1,169 unique image files
- Images downloaded to `websiteimages/` directory

**Structure:**
```json
{
  "generatedAt": "2026-02-10T10:06:28.605273",
  "stats": { "totalPages": 252, ... },
  "pages": [
    {
      "pageType": "tour",
      "tourCode": "WR4",
      "tourName": "White Rim 4-Day",
      "slug": "white-rim-4-day",
      "wordpressUrl": "https://rimtours.com/tours/white-rim-4-day/",
      "outlineId": "cf145a93-...",
      "images": {
        "hero": "websiteimages/tours/white-rim-4-day/hero.jpg",
        "gallery": ["websiteimages/tours/white-rim-4-day/gallery-1.jpg"],
        "slider": ["websiteimages/slider/white-rim-sunset.jpg"]
      }
    }
  ]
}
```

### 4. **WEBSITE_AGENT_PROMPT.md**
**What it is:** Original site structure guide (from Phase 1)
**Key info:**
- Tour filter criteria (type, difficulty, region, duration, season)
- Site navigation structure
- Booking flow and Arctic integration
- WordPress URL mappings

### 5. **ARCTIC_API_GUIDE.md**
**What it is:** Arctic Reservations API documentation
**Key info:**
- How to fetch live availability
- Pricing data structure
- Trip type IDs (from D1: `arctic_id` field)

---

## 🏗️ System Architecture (What's Already Built)

```
┌─────────────────────────────────────────────────────────────┐
│  OUTLINE (outline.sandland.us)                              │
│  Human-friendly CMS where Eric edits tour content           │
└────────────────┬────────────────────────────────────────────┘
                 │ (GitHub Actions syncs hourly)
                 ↓
┌─────────────────────────────────────────────────────────────┐
│  CLOUDFLARE D1 (rim-tours-db)                               │
│  Structured database with 48 tours                          │
│  - tours table (descriptions, details, metadata)            │
│  - tour_images, tour_marketing_copy tables                  │
└────────────────┬────────────────────────────────────────────┘
                 │ (API endpoints)
                 ↓
┌─────────────────────────────────────────────────────────────┐
│  D1 SYNC WORKER (outline-d1-sync.eric-c5f.workers.dev)     │
│  GET /api/tours - List tours with filters                   │
│  GET /api/tours/:code - Single tour details                 │
└─────────────────────────────────────────────────────────────┘
                 │
                 ↓ YOUR WORK STARTS HERE
┌─────────────────────────────────────────────────────────────┐
│  WEBSITE (Cloudflare Pages)                                 │
│  - Static HTML generated at build time                      │
│  - Client-side JS fetches live Arctic availability          │
└─────────────────────────────────────────────────────────────┘
```

---

## 📦 Data Sources

### Source 1: D1 Database (Static Tour Info)
**Fetch at build time** to generate static HTML

**Example:**
```javascript
// In build script
const response = await fetch(
  'https://outline-d1-sync.eric-c5f.workers.dev/api/tours'
);
const { tours } = await response.json();

// Generate static HTML for each tour
for (const tour of tours) {
  const html = generateTourPage(tour);
  await writeFile(`dist/tours/${tour.tour_code}.html`, html);
}
```

**What you get:**
- Tour descriptions, itineraries, meeting info
- Difficulty, duration, region, season
- Arctic ID (for fetching live availability)
- Marketing copy variations
- Metadata (WordPress URLs, Outline IDs)

**What you DON'T get:**
- ❌ Live availability (fetch from Arctic API)
- ❌ Current pricing (fetch from Arctic API)

### Source 2: Arctic API (Live Availability)
**Fetch at runtime** (client-side or via proxy Worker)

**Don't expose credentials to browser!** Create a proxy Worker:

```typescript
// workers/arctic-proxy/src/index.ts
export default {
  async fetch(request: Request, env: Env) {
    const arcticId = extractIdFromUrl(request.url);
    const arctic = new ArcticClient(env);
    const availability = await arctic.get_full_schedule(arcticId);

    return Response.json({
      upcomingDates: availability.future,
      pricing: availability.pricing
    });
  }
};
```

Then fetch client-side:
```javascript
// On tour page
fetch(`/api/availability/${tour.arctic_id}`)
  .then(r => r.json())
  .then(data => renderAvailability(data));
```

### Source 3: Image Manifest (Tour Images)
**Use at build time** to embed correct images in HTML

```javascript
import imageManifest from './image_manifest.json';

function getToursImages(tourCode) {
  const page = imageManifest.pages.find(p => p.tourCode === tourCode);
  return page?.images || {};
}

// In tour page template
const images = getTourImages('WR4');
const heroImage = images.hero; // "websiteimages/tours/white-rim-4-day/hero.jpg"
```

**Images are in:** `websiteimages/` directory (not in git, but available locally)

---

## 🗂️ Tour Data Structure (from D1)

**Example tour object:**
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
  "description": "Four days of epic singletrack riding through Canyonlands...",
  "meeting_info": "Meet at Rim Tours shop at 8:00 AM...",
  "what_to_bring": "Riding clothes, sunscreen, water bottle...",
  "itinerary_overview": "## Day 1\n\nWe'll start by...",
  "wordpress_url": "https://rimtours.com/tours/white-rim-4-day/",
  "outline_id": "cf145a93-...",
  "price_range": "$1000-2000",
  "has_ebike": 1,
  "is_private": 0,
  "marketingCopy": [
    {
      "style": "Adventure Seekers",
      "description": "Embark on an unforgettable 4-day journey..."
    }
  ]
}
```

---

## 🎨 Website Pages to Build

### 1. Homepage
- Hero section with featured tours
- Tour type filters (Day Tours, Multi-Day, etc.)
- Call-to-action (Book Now)

### 2. Tour Listings Page (`/tours`)
**Filters:**
- Tour Type (Day Tour, Multi-Day Camping, Bed & Breakfast)
- Difficulty (Beginner, Intermediate, Advanced)
- Region (Moab Area, Grand Canyon, Crested Butte, etc.)
- Duration (1 day, 3-5 days, 6+ days)
- Season (Spring, Summer, Fall, Winter)

**Data source:** `GET /api/tours?region=Moab%20Area&difficulty=Intermediate`

### 3. Tour Detail Pages (`/tours/:code`)
**Sections:**
- Hero image + tour name
- Quick facts (difficulty, duration, region, season)
- Description
- Itinerary (day-by-day)
- Meeting info
- What to bring
- **Live availability calendar** (client-side fetch from Arctic)
- Pricing options (from Arctic)
- Book Now button (links to Arctic booking iframe)

**Data sources:**
- Static content: `GET /api/tours/WR4`
- Images: `image_manifest.json`
- Live availability: Arctic API

### 4. About/Info Pages
- About Rim Tours
- Guides & staff
- FAQs
- Contact

---

## 🖼️ Using Images

### Image Types in Manifest

**hero** - Main tour image (1 per tour)
**gallery** - Additional tour photos (multiple per tour)
**slider** - Homepage/banner images
**inline** - Content images (within descriptions)

### Example Usage

```javascript
import imageManifest from './image_manifest.json';

function buildTourPage(tour) {
  const page = imageManifest.pages.find(p => p.tourCode === tour.tour_code);

  return `
    <div class="hero">
      <img src="/${page.images.hero}" alt="${tour.tour_name}" />
    </div>

    <div class="gallery">
      ${page.images.gallery?.map(img => `
        <img src="/${img}" alt="${tour.tour_name} gallery" />
      `).join('')}
    </div>
  `;
}
```

### Image Locations

All images are in `websiteimages/` directory:
```
websiteimages/
  tours/
    white-rim-4-day/
      hero.jpg
      gallery-1.jpg
      gallery-2.jpg
  slider/
    moab-sunset.jpg
  pages/
    about-us/
      team-photo.jpg
```

---

## 🔐 Security Notes

**Public endpoints (safe to call from build scripts):**
- ✅ `GET /api/tours`
- ✅ `GET /api/tours/:code`

**Protected endpoints (require API key):**
- 🔒 `POST /api/sync-now` (admin only)

**Arctic API credentials:**
- ❌ **Never expose to browser**
- ✅ Use proxy Worker for availability endpoints
- ✅ Keep credentials in Worker environment variables

---

## 🚀 Build Process (Recommended)

### Step 1: Setup Project

```bash
# Choose framework (Astro recommended)
npm create astro@latest rim-tours-website
cd rim-tours-website
```

### Step 2: Fetch Tour Data at Build Time

```javascript
// src/data/tours.js
export async function getTours() {
  const response = await fetch(
    'https://outline-d1-sync.eric-c5f.workers.dev/api/tours'
  );
  return await response.json();
}

export async function getTourImages(tourCode) {
  const manifest = await import('../data/image_manifest.json');
  return manifest.pages.find(p => p.tourCode === tourCode)?.images;
}
```

### Step 3: Generate Static Pages

```astro
---
// src/pages/tours/[code].astro
import { getTours, getTourImages } from '../../data/tours.js';

export async function getStaticPaths() {
  const { tours } = await getTours();
  return tours.map(tour => ({
    params: { code: tour.tour_code },
    props: { tour }
  }));
}

const { tour } = Astro.props;
const images = await getTourImages(tour.tour_code);
---

<html>
  <head>
    <title>{tour.tour_name} | Rim Tours</title>
  </head>
  <body>
    <img src={images.hero} alt={tour.tour_name} />
    <h1>{tour.tour_name}</h1>
    <p>{tour.description}</p>

    <!-- Client-side availability -->
    <div id="availability" data-arctic-id={tour.arctic_id}></div>
  </body>
</html>
```

### Step 4: Add Client-Side Availability

```javascript
// src/scripts/availability.js
export async function loadAvailability(arcticId) {
  const response = await fetch(`/api/availability/${arcticId}`);
  const data = await response.json();

  // Render available dates
  return data.upcomingDates.map(date => ({
    date: date.start_date,
    spotsAvailable: date.spots_available,
    spotsTotal: date.spots_total
  }));
}
```

### Step 5: Deploy to Cloudflare Pages

```bash
npm run build
# Output goes to dist/

# Deploy
npx wrangler pages deploy dist
```

---

## 📊 Performance Targets

✅ **First Contentful Paint:** < 1s
✅ **Largest Contentful Paint:** < 2.5s
✅ **Cumulative Layout Shift:** < 0.1
✅ **Time to Interactive:** < 3s

**How to achieve:**
- Static HTML (instant load)
- Optimize images (WebP, lazy loading)
- Minimal JavaScript (only for availability)
- CDN caching (Cloudflare Pages)

---

## 🧪 Testing Checklist

- [ ] All tour pages generate successfully
- [ ] Filters work correctly (region, difficulty, etc.)
- [ ] Images load properly
- [ ] Live availability displays on tour pages
- [ ] Booking links work (Arctic iframe)
- [ ] Mobile responsive
- [ ] SEO metadata present (title, description, Open Graph)
- [ ] Fast page loads (< 2s)

---

## 📁 File Locations

**On this machine:**
- Tour data API: `https://outline-d1-sync.eric-c5f.workers.dev`
- Image manifest: `/home/eric/code/data-cleaning-projects/image_manifest.json`
- Downloaded images: `/home/eric/code/data-cleaning-projects/websiteimages/`
- API docs: `/home/eric/code/data-cleaning-projects/D1_API_DOCUMENTATION.md`
- Architecture guide: `/home/eric/code/data-cleaning-projects/STATIC_WEBSITE_ARCHITECTURE.md`

**In GitHub:**
- Repo: `frigiddesert/data-cleaning-projects`
- Worker code: `workers/outline-d1-sync/`
- Documentation: `*.md` files in root

---

## 🎯 Success Criteria

**The website is done when:**
1. ✅ All 48 tours have static pages
2. ✅ Tour filters work (region, difficulty, duration)
3. ✅ Live availability shows on tour pages
4. ✅ Images display correctly
5. ✅ Booking links work
6. ✅ Mobile responsive
7. ✅ Fast (< 2s page loads)
8. ✅ SEO optimized (meta tags, sitemap)
9. ✅ Deployed to Cloudflare Pages

---

## 💡 Pro Tips

1. **Start with 2-3 tours** - Build the template, then scale to all 48
2. **Use Astro** - Best for static sites, great DX, fast builds
3. **Cache aggressively** - Static HTML = fast
4. **Lazy load images** - Only load what's visible
5. **Test mobile first** - Most users are on mobile
6. **Use Arctic proxy Worker** - Never expose API credentials to browser

---

## 🆘 Questions? Check These Files

- **API not working?** → `D1_API_DOCUMENTATION.md`
- **Images not found?** → `image_manifest.json`
- **Architecture questions?** → `STATIC_WEBSITE_ARCHITECTURE.md`
- **Arctic API issues?** → `ARCTIC_API_GUIDE.md`
- **Site structure unclear?** → `WEBSITE_AGENT_PROMPT.md`

---

**Ready to build!** Start with `STATIC_WEBSITE_ARCHITECTURE.md` and let's make this site fast! ⚡
