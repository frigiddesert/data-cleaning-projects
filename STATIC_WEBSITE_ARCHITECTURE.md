# Static Website Architecture Guide

## 🎯 Goal

Serve **static HTML pages** (fast, cached on CDN) while showing **live tour availability** (fetched client-side from Arctic).

---

## 🏗️ Recommended Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  BUILD TIME (Cloudflare Pages deployment)                  │
│                                                             │
│  1. Build script fetches ALL tour data from D1              │
│  2. Generates static HTML for each tour page                │
│  3. Generates tour listing pages (filtered by region, etc.) │
│  4. Deploys to Cloudflare Pages CDN                         │
│                                                             │
│  Output: Static HTML files (no compute on page load)        │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  RUNTIME (User visits page)                                 │
│                                                             │
│  1. Static HTML loads instantly from CDN (tour info)        │
│  2. JavaScript fetches live availability from Arctic        │
│  3. JavaScript updates page with available dates/pricing    │
│                                                             │
│  Result: Fast initial load + live booking data             │
└─────────────────────────────────────────────────────────────┘
```

---

## 📦 Static Site Generation (SSG)

### Build Script Example

**File:** `build-tours.js` (runs during Cloudflare Pages build)

```javascript
// Fetch tour data from D1 at build time
async function fetchTourData() {
  const response = await fetch(
    'https://outline-d1-sync.eric-c5f.workers.dev/api/tours'
  );
  return await response.json();
}

// Generate static HTML for each tour
async function buildTourPages() {
  const { tours } = await fetchTourData();

  for (const tour of tours) {
    const html = `
<!DOCTYPE html>
<html>
<head>
  <title>${tour.tour_name} | Rim Tours</title>
  <meta name="description" content="${tour.description}">
  <!-- SEO metadata pre-rendered -->
</head>
<body>
  <h1>${tour.tour_name}</h1>
  <p>${tour.description}</p>

  <div class="tour-details">
    <p><strong>Difficulty:</strong> ${tour.difficulty}</p>
    <p><strong>Duration:</strong> ${tour.duration_days} days</p>
    <p><strong>Region:</strong> ${tour.region}</p>
  </div>

  <div class="itinerary">
    ${tour.itinerary_overview || ''}
  </div>

  <!-- Live availability loads client-side -->
  <div id="availability" data-arctic-id="${tour.arctic_id}">
    <p>Loading availability...</p>
  </div>

  <script>
    // Client-side: Fetch live Arctic data
    const arcticId = ${tour.arctic_id};

    fetch(\`/api/availability/\${arcticId}\`)
      .then(r => r.json())
      .then(data => {
        document.getElementById('availability').innerHTML =
          renderAvailability(data);
      });
  </script>
</body>
</html>
    `;

    // Write static file
    await fs.writeFile(\`dist/tours/\${tour.tour_code}.html\`, html);
  }
}

buildTourPages();
```

---

## 🔌 Live Availability (Client-Side)

### Option 1: Direct Arctic API Call (Client-Side)

**Not recommended** - Exposes Arctic credentials to browser

### Option 2: Proxy Worker (Recommended)

Create a lightweight Worker that proxies Arctic API calls:

**File:** `workers/arctic-proxy/src/index.ts`

```typescript
export default {
  async fetch(request: Request, env: Env) {
    const url = new URL(request.url);
    const arcticId = url.pathname.match(/\/api\/availability\/(\d+)/)?.[1];

    if (!arcticId) {
      return new Response('Not found', { status: 404 });
    }

    // Fetch from Arctic API (server-side, credentials safe)
    const arcticClient = new ArcticClient(env);
    const availability = await arcticClient.get_full_schedule(parseInt(arcticId));
    const pricing = await arcticClient.get_trip_pricing_summary(parseInt(arcticId));

    return new Response(JSON.stringify({
      upcomingDates: availability.future,
      pricing: pricing.pricing,
      lastUpdated: new Date().toISOString()
    }), {
      headers: {
        'Content-Type': 'application/json',
        'Cache-Control': 'public, max-age=300' // Cache 5 min
      }
    });
  }
};
```

Deploy as: `https://arctic-proxy.eric-c5f.workers.dev`

### Client-Side JavaScript

```javascript
// On tour page
async function loadAvailability(arcticId) {
  const response = await fetch(
    `https://arctic-proxy.eric-c5f.workers.dev/api/availability/${arcticId}`
  );
  const data = await response.json();

  // Render available dates
  const html = data.upcomingDates
    .slice(0, 10)
    .map(date => `
      <div class="date-card">
        <span class="date">${date.start_date}</span>
        <span class="spots">${date.spots_available}/${date.spots_total} spots</span>
        <button onclick="bookTour('${date.start_date}')">Book Now</button>
      </div>
    `)
    .join('');

  document.getElementById('availability').innerHTML = html;
}
```

---

## 📁 Project Structure

```
your-website/
├── build-tours.js              # Build script (fetches D1, generates HTML)
├── dist/                       # Static output (deployed to Pages)
│   ├── index.html              # Homepage
│   ├── tours/
│   │   ├── WR4.html            # Static tour pages
│   │   ├── KOKO5.html
│   │   └── ...
│   └── js/
│       └── availability.js     # Client-side availability fetcher
├── workers/
│   └── arctic-proxy/           # Worker to proxy Arctic API
│       └── src/index.ts
└── wrangler.toml               # Pages + Workers config
```

---

## ⚡ Cloudflare Pages Build Configuration

**Build command:**
```bash
node build-tours.js && npm run build
```

**Build output directory:**
```
dist/
```

**Environment variables:**
```
TOURS_API_URL=https://outline-d1-sync.eric-c5f.workers.dev
```

---

## 🔄 Rebuild Trigger

**Option 1: Manual Rebuild**
- Go to Cloudflare Pages dashboard
- Click "Retry deployment"
- Or push to main branch

**Option 2: Automatic Rebuild (via GitHub Action)**

Add to `.github/workflows/outline-d1-sync.yml`:

```yaml
- name: Trigger Pages rebuild
  if: success()
  run: |
    # Trigger Cloudflare Pages deployment after successful D1 sync
    curl -X POST "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/pages/projects/$PROJECT_NAME/deployments" \
      -H "Authorization: Bearer $CF_API_TOKEN" \
      -H "Content-Type: application/json" \
      -d '{"branch":"main"}'
  env:
    CF_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
    CF_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
    PROJECT_NAME: "rim-tours-website"
```

**Rebuild flow:**
1. You edit tour in Outline
2. GitHub Action syncs Outline → D1 (hourly)
3. After successful D1 sync, trigger Pages rebuild
4. Pages build fetches updated tour data from D1
5. Generates fresh static HTML
6. Deploys to CDN

---

## 🎨 Framework Options

### Option 1: Plain HTML/JS (Simplest)
- Build script generates HTML files
- No framework needed
- Full control, very fast

### Option 2: Astro (Recommended for SSG)
```bash
npm create astro@latest
```

**Example Astro page:**
```astro
---
// src/pages/tours/[code].astro
export async function getStaticPaths() {
  const response = await fetch('https://outline-d1-sync.eric-c5f.workers.dev/api/tours');
  const { tours } = await response.json();

  return tours.map(tour => ({
    params: { code: tour.tour_code },
    props: { tour }
  }));
}

const { tour } = Astro.props;
---

<html>
  <head>
    <title>{tour.tour_name} | Rim Tours</title>
  </head>
  <body>
    <h1>{tour.tour_name}</h1>
    <p>{tour.description}</p>

    <!-- Client-side availability -->
    <div id="availability" data-arctic-id={tour.arctic_id}></div>

    <script>
      import { loadAvailability } from '../js/availability.js';
      const arcticId = document.getElementById('availability').dataset.arcticId;
      loadAvailability(arcticId);
    </script>
  </body>
</html>
```

### Option 3: Next.js (with Static Export)
```bash
npx create-next-app@latest
```

**next.config.js:**
```javascript
module.exports = {
  output: 'export', // Static HTML export
  images: { unoptimized: true }
};
```

---

## 🚀 Performance Benefits

**Static HTML:**
- ✅ Instant page load (CDN cached)
- ✅ Perfect SEO (pre-rendered HTML)
- ✅ No server compute on page load
- ✅ Scales to millions of requests (CDN)

**Client-side availability:**
- ✅ Always fresh data from Arctic
- ✅ Doesn't block initial page load
- ✅ Cached for 5 minutes (reduces Arctic API calls)

---

## 🔐 Security Summary

### Protected Endpoints
- ✅ `POST /api/sync-now` - Requires `X-API-Key` header
- ✅ Arctic credentials - Hidden in Worker (not exposed to browser)

### Public Endpoints (Read-Only)
- ✅ `GET /api/tours` - Tour listings (public data)
- ✅ `GET /api/tours/:code` - Tour details (public data)
- ✅ `GET /api/availability/:id` - Live Arctic data (proxied through Worker)

**Why this is safe:**
- Tour data is public anyway (shown on website)
- No write access from public endpoints
- Arctic credentials never exposed to browser
- Sync endpoint protected by API key

---

## 📊 Data Flow Summary

```
┌─────────────┐
│  OUTLINE    │  You edit tours here
└──────┬──────┘
       │ (hourly sync)
       ↓
┌─────────────┐
│  D1 DATABASE│  Structured tour data
└──────┬──────┘
       │ (build time fetch)
       ↓
┌─────────────┐
│ STATIC HTML │  Pre-rendered tour pages
│  (CDN Cache)│  - Descriptions, itineraries
└──────┬──────┘  - Metadata, images
       │ (user visits)
       ↓
┌─────────────┐
│  BROWSER    │  Loads static HTML instantly
└──────┬──────┘
       │ (client-side JS fetch)
       ↓
┌─────────────┐
│ ARCTIC API  │  Live availability/pricing
│ (via Worker)│
└─────────────┘
```

---

## 🎯 Implementation Steps

1. ✅ **D1 database** - Already set up (48 tours synced)
2. ✅ **Sync automation** - GitHub Actions running hourly
3. ⬜ **Arctic proxy Worker** - Create lightweight Worker for availability
4. ⬜ **Build script** - Fetch D1 data, generate static HTML
5. ⬜ **Deploy to Pages** - Upload static files to Cloudflare Pages
6. ⬜ **Client-side JS** - Fetch availability, update page dynamically

---

## 📚 Next Steps

1. **Choose framework**: Astro (recommended), plain HTML, or Next.js
2. **Create build script**: Fetch D1 → Generate HTML
3. **Create Arctic proxy Worker**: Safe availability endpoint
4. **Deploy to Cloudflare Pages**: Static files on CDN
5. **Test**: Verify static load + live availability

---

**Result:** Lightning-fast static pages with live booking data! ⚡

**Cost:** Still $0/month (Pages free tier: 500 builds/month, unlimited requests)
