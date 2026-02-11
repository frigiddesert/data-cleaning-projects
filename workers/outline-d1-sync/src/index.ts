/**
 * Outline → D1 Sync Worker
 *
 * Polls Outline API for tour document changes and syncs to D1.
 * Provides API endpoints for website to query tour data.
 *
 * Cron: Runs every 30 minutes
 * Endpoints:
 *   GET /api/sync-status - Sync statistics
 *   POST /api/sync-now - Manual trigger
 *   GET /api/tours - List tours with filters
 *   GET /api/tours/:code - Single tour details
 */

import { Env, OutlineListResponse, OutlineInfoResponse, ParsedTour, SyncStats } from './types';
import { parseTourDocument } from './parser';

export default {
  /**
   * Cron trigger - polls Outline every 30 minutes
   */
  async scheduled(event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    console.log('Cron trigger: Starting Outline → D1 sync');

    try {
      const stats = await syncOutlineToD1(env);
      console.log('Sync complete:', stats);

      // Update sync metadata
      await env.DB.prepare(
        'UPDATE sync_metadata SET value = ?, updated_at = datetime("now") WHERE key = ?'
      )
        .bind('success', 'sync_status')
        .run();
    } catch (error) {
      console.error('Sync failed:', error);

      // Update sync metadata
      await env.DB.prepare(
        'UPDATE sync_metadata SET value = ?, updated_at = datetime("now") WHERE key = ?'
      )
        .bind('error', 'sync_status')
        .run();
    }
  },

  /**
   * HTTP request handler
   */
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);
    const path = url.pathname;

    // CORS headers
    const corsHeaders = {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, X-API-Key',
    };

    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: corsHeaders });
    }

    // Protect write endpoints with API key
    if (request.method === 'POST' && path === '/api/sync-now') {
      const apiKey = request.headers.get('X-API-Key');
      if (!env.API_KEY || apiKey !== env.API_KEY) {
        return jsonResponse(
          { error: 'Unauthorized' },
          { ...corsHeaders, 'WWW-Authenticate': 'X-API-Key' },
          401
        );
      }
    }

    try {
      // Sync status endpoint
      if (path === '/api/sync-status' && request.method === 'GET') {
        const status = await getSyncStatus(env);
        return jsonResponse(status, corsHeaders);
      }

      // Manual sync trigger
      if (path === '/api/sync-now' && request.method === 'POST') {
        const stats = await syncOutlineToD1(env);
        return jsonResponse({ success: true, stats }, corsHeaders);
      }

      // List tours with filters
      if (path === '/api/tours' && request.method === 'GET') {
        const filters = {
          type: url.searchParams.get('type'),
          difficulty: url.searchParams.get('difficulty'),
          region: url.searchParams.get('region'),
          duration: url.searchParams.get('duration'),
        };
        const tours = await getTours(env, filters);
        return jsonResponse({ tours }, corsHeaders);
      }

      // Single tour details
      const tourMatch = path.match(/^\/api\/tours\/([A-Za-z0-9\-()]+)$/);
      if (tourMatch && request.method === 'GET') {
        const tourCode = tourMatch[1];
        const tour = await getTourDetails(env, tourCode);
        if (!tour) {
          return jsonResponse({ error: 'Tour not found' }, corsHeaders, 404);
        }
        return jsonResponse(tour, corsHeaders);
      }

      return jsonResponse({ error: 'Not found' }, corsHeaders, 404);
    } catch (error) {
      console.error('Request error:', error);
      return jsonResponse(
        { error: 'Internal server error', message: (error as Error).message },
        corsHeaders,
        500
      );
    }
  },
};

/**
 * Main sync logic: Poll Outline and update D1
 */
async function syncOutlineToD1(env: Env): Promise<SyncStats> {
  const stats: SyncStats = {
    totalProcessed: 0,
    inserted: 0,
    updated: 0,
    errors: 0,
    lastSync: new Date().toISOString(),
  };

  // Get last sync timestamp
  const lastSyncResult = await env.DB.prepare(
    'SELECT value FROM sync_metadata WHERE key = ?'
  )
    .bind('last_sync')
    .first<{ value: string }>();

  const lastSync = lastSyncResult?.value || '1970-01-01T00:00:00Z';

  // Fetch tour documents from both folders
  const dayTours = await fetchOutlineDocuments(env, env.OUTLINE_DAY_TOURS_DOC_ID);
  const mdTours = await fetchOutlineDocuments(env, env.OUTLINE_MD_TOURS_DOC_ID);
  const allTours = [...dayTours, ...mdTours];

  console.log(`Found ${allTours.length} tour documents in Outline`);

  // Filter to only changed documents
  const changedTours = allTours.filter((doc) => doc.updatedAt > lastSync);
  console.log(`${changedTours.length} tours changed since ${lastSync}`);

  // Process each changed tour
  for (const doc of changedTours) {
    stats.totalProcessed++;

    try {
      // Fetch full document content
      const fullDoc = await fetchOutlineDocument(env, doc.id);
      if (!fullDoc) {
        console.warn(`Failed to fetch document ${doc.id}`);
        stats.errors++;
        continue;
      }

      // Parse document
      const parsed = parseTourDocument(fullDoc);
      if (!parsed) {
        console.warn(`Failed to parse document ${doc.id} (${doc.title})`);
        stats.errors++;
        continue;
      }

      // Check if tour exists
      const existing = await env.DB.prepare(
        'SELECT tour_code FROM tours WHERE tour_code = ?'
      )
        .bind(parsed.tourCode)
        .first();

      if (existing) {
        // Update existing tour
        await updateTour(env, parsed);
        stats.updated++;
        console.log(`Updated tour: ${parsed.tourCode}`);
      } else {
        // Insert new tour
        await insertTour(env, parsed);
        stats.inserted++;
        console.log(`Inserted tour: ${parsed.tourCode}`);
      }
    } catch (error) {
      console.error(`Error processing tour ${doc.id}:`, error);
      stats.errors++;
    }
  }

  // Update last sync timestamp
  await env.DB.prepare(
    'UPDATE sync_metadata SET value = ?, updated_at = datetime("now") WHERE key = ?'
  )
    .bind(new Date().toISOString(), 'last_sync')
    .run();

  return stats;
}

/**
 * Fetch document list from Outline
 */
async function fetchOutlineDocuments(env: Env, parentId: string): Promise<Array<{ id: string; title: string; updatedAt: string }>> {
  const response = await fetch(`${env.OUTLINE_API_URL}/documents.list`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${env.OUTLINE_API_KEY}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      parentDocumentId: parentId,
      limit: 100,
    }),
  });

  if (!response.ok) {
    throw new Error(`Outline API error: ${response.status} ${response.statusText}`);
  }

  const data: OutlineListResponse = await response.json();
  return data.data.map((doc) => ({
    id: doc.id,
    title: doc.title,
    updatedAt: doc.updatedAt,
  }));
}

/**
 * Fetch full document from Outline
 */
async function fetchOutlineDocument(env: Env, docId: string): Promise<{ id: string; title: string; text: string; updatedAt: string } | null> {
  const response = await fetch(`${env.OUTLINE_API_URL}/documents.info`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${env.OUTLINE_API_KEY}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ id: docId }),
  });

  if (!response.ok) {
    console.error(`Failed to fetch document ${docId}: ${response.status}`);
    return null;
  }

  const data: OutlineInfoResponse = await response.json();
  return data.data;
}

/**
 * Insert new tour into D1
 */
async function insertTour(env: Env, tour: ParsedTour): Promise<void> {
  // Insert tour
  await env.DB.prepare(
    `INSERT INTO tours (
      tour_code, tour_name, tour_type, difficulty, duration_days, duration_nights,
      region, season_start, season_end, arctic_id, description, meeting_info,
      what_to_bring, itinerary_overview, booking_notes, wordpress_url,
      outline_id, outline_updated_at, synced_at, price_range, has_ebike, is_private
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), ?, ?, ?)`
  )
    .bind(
      tour.tourCode,
      tour.tourName,
      tour.tourType,
      tour.difficulty,
      tour.durationDays,
      tour.durationNights,
      tour.region,
      tour.seasonStart,
      tour.seasonEnd,
      tour.arcticId,
      tour.description,
      tour.meetingInfo,
      tour.whatToBring,
      tour.itineraryOverview,
      tour.bookingNotes,
      tour.wordpressUrl,
      tour.outlineId,
      tour.outlineUpdatedAt,
      tour.priceRange,
      tour.hasEbike ? 1 : 0,
      tour.isPrivate ? 1 : 0
    )
    .run();

  // Insert marketing copy
  for (const copy of tour.marketingCopy) {
    await env.DB.prepare(
      'INSERT INTO tour_marketing_copy (tour_code, style, description) VALUES (?, ?, ?)'
    )
      .bind(tour.tourCode, copy.style, copy.description)
      .run();
  }
}

/**
 * Update existing tour in D1
 */
async function updateTour(env: Env, tour: ParsedTour): Promise<void> {
  // Update tour
  await env.DB.prepare(
    `UPDATE tours SET
      tour_name = ?, tour_type = ?, difficulty = ?, duration_days = ?, duration_nights = ?,
      region = ?, season_start = ?, season_end = ?, arctic_id = ?, description = ?,
      meeting_info = ?, what_to_bring = ?, itinerary_overview = ?, booking_notes = ?,
      wordpress_url = ?, outline_id = ?, outline_updated_at = ?, synced_at = datetime('now'),
      price_range = ?, has_ebike = ?, is_private = ?
    WHERE tour_code = ?`
  )
    .bind(
      tour.tourName,
      tour.tourType,
      tour.difficulty,
      tour.durationDays,
      tour.durationNights,
      tour.region,
      tour.seasonStart,
      tour.seasonEnd,
      tour.arcticId,
      tour.description,
      tour.meetingInfo,
      tour.whatToBring,
      tour.itineraryOverview,
      tour.bookingNotes,
      tour.wordpressUrl,
      tour.outlineId,
      tour.outlineUpdatedAt,
      tour.priceRange,
      tour.hasEbike ? 1 : 0,
      tour.isPrivate ? 1 : 0,
      tour.tourCode
    )
    .run();

  // Delete old marketing copy and re-insert
  await env.DB.prepare('DELETE FROM tour_marketing_copy WHERE tour_code = ?')
    .bind(tour.tourCode)
    .run();

  for (const copy of tour.marketingCopy) {
    await env.DB.prepare(
      'INSERT INTO tour_marketing_copy (tour_code, style, description) VALUES (?, ?, ?)'
    )
      .bind(tour.tourCode, copy.style, copy.description)
      .run();
  }
}

/**
 * Get sync status
 */
async function getSyncStatus(env: Env): Promise<any> {
  const metadata = await env.DB.prepare(
    'SELECT key, value, updated_at FROM sync_metadata'
  ).all();

  const tourCount = await env.DB.prepare(
    'SELECT COUNT(*) as count FROM tours WHERE is_active = 1'
  ).first<{ count: number }>();

  return {
    lastSync: metadata.results?.find((m: any) => m.key === 'last_sync')?.value,
    status: metadata.results?.find((m: any) => m.key === 'sync_status')?.value,
    totalTours: tourCount?.count || 0,
  };
}

/**
 * Get tours with optional filters
 */
async function getTours(
  env: Env,
  filters: { type?: string | null; difficulty?: string | null; region?: string | null; duration?: string | null }
): Promise<any[]> {
  let query = 'SELECT * FROM tours WHERE is_active = 1';
  const bindings: any[] = [];

  if (filters.type) {
    query += ' AND tour_type = ?';
    bindings.push(filters.type);
  }
  if (filters.difficulty) {
    query += ' AND difficulty = ?';
    bindings.push(filters.difficulty);
  }
  if (filters.region) {
    query += ' AND region = ?';
    bindings.push(filters.region);
  }
  if (filters.duration) {
    query += ' AND duration_days = ?';
    bindings.push(parseInt(filters.duration, 10));
  }

  const result = await env.DB.prepare(query).bind(...bindings).all();
  return result.results || [];
}

/**
 * Get single tour details
 */
async function getTourDetails(env: Env, tourCode: string): Promise<any | null> {
  const tour = await env.DB.prepare(
    'SELECT * FROM tours WHERE tour_code = ? AND is_active = 1'
  )
    .bind(tourCode)
    .first();

  if (!tour) return null;

  // Get marketing copy
  const marketingCopy = await env.DB.prepare(
    'SELECT style, description FROM tour_marketing_copy WHERE tour_code = ?'
  )
    .bind(tourCode)
    .all();

  return {
    ...tour,
    marketingCopy: marketingCopy.results || [],
  };
}

/**
 * Helper: JSON response
 */
function jsonResponse(data: any, headers: Record<string, string> = {}, status = 200): Response {
  return new Response(JSON.stringify(data, null, 2), {
    status,
    headers: {
      'Content-Type': 'application/json',
      ...headers,
    },
  });
}
