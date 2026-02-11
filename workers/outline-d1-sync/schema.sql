-- Rim Tours D1 Database Schema
-- This schema stores static tour data synced from Outline
-- Arctic availability/pricing data is NOT stored here (fetched live)

-- Core tour information
CREATE TABLE IF NOT EXISTS tours (
  tour_code TEXT PRIMARY KEY,          -- WR4, KOKO5, etc. (from title)
  tour_name TEXT NOT NULL,             -- "White Rim 4-Day"
  tour_type TEXT,                      -- "Multi-Day Camping", "Day Tour"
  difficulty TEXT,                     -- "Intermediate", "Beginner", "Advanced"
  duration_days INTEGER,               -- 4, 5, 1, etc.
  duration_nights INTEGER,             -- 3, 4, 0, etc.
  region TEXT,                         -- "Moab", "Grand Canyon", "Crested Butte"
  season_start TEXT,                   -- "March"
  season_end TEXT,                     -- "November"

  -- Arctic integration (for fetching live data)
  arctic_id INTEGER,                   -- 191, 260, etc. (from Reference table)

  -- Content from Outline
  description TEXT,                    -- Brief description blockquote
  meeting_info TEXT,                   -- Where/when to meet
  what_to_bring TEXT,                  -- Packing list
  itinerary_overview TEXT,             -- Full itinerary markdown
  booking_notes TEXT,                  -- Special booking instructions

  -- URLs and IDs
  wordpress_url TEXT,                  -- Legacy WP URL
  outline_id TEXT UNIQUE,              -- Outline document ID

  -- Metadata for sync tracking
  outline_updated_at TEXT,             -- ISO timestamp from Outline
  synced_at TEXT,                      -- When we last synced this tour
  is_active INTEGER DEFAULT 1,         -- 0 if deprecated/archived

  -- Computed fields for filtering/search
  price_range TEXT,                    -- "$1000-2000", "$2000-3000" (computed)
  has_ebike INTEGER DEFAULT 0,         -- 1 if ebike tour
  is_private INTEGER DEFAULT 0         -- 1 if private only tour
);

-- Images associated with tours
CREATE TABLE IF NOT EXISTS tour_images (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tour_code TEXT NOT NULL,
  image_type TEXT NOT NULL,            -- "hero", "gallery", "inline"
  image_path TEXT NOT NULL,            -- "tours/white-rim-4-day/hero.jpg"
  image_url TEXT,                      -- Full URL if hosted externally
  alt_text TEXT,                       -- Accessibility text
  sort_order INTEGER DEFAULT 0,
  FOREIGN KEY (tour_code) REFERENCES tours(tour_code) ON DELETE CASCADE
);

-- Marketing copy variations (from table at bottom of Outline docs)
CREATE TABLE IF NOT EXISTS tour_marketing_copy (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tour_code TEXT NOT NULL,
  style TEXT NOT NULL,                 -- "Adventure Seekers", "Families", etc.
  description TEXT NOT NULL,           -- The marketing copy
  FOREIGN KEY (tour_code) REFERENCES tours(tour_code) ON DELETE CASCADE
);

-- Track sync state to avoid re-processing unchanged docs
CREATE TABLE IF NOT EXISTS sync_metadata (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL             -- ISO timestamp
);

-- Indexes for fast queries
CREATE INDEX IF NOT EXISTS idx_tours_type ON tours(tour_type);
CREATE INDEX IF NOT EXISTS idx_tours_difficulty ON tours(difficulty);
CREATE INDEX IF NOT EXISTS idx_tours_region ON tours(region);
CREATE INDEX IF NOT EXISTS idx_tours_duration ON tours(duration_days);
CREATE INDEX IF NOT EXISTS idx_tours_active ON tours(is_active);
CREATE INDEX IF NOT EXISTS idx_tours_updated ON tours(outline_updated_at);
CREATE INDEX IF NOT EXISTS idx_tour_images_code ON tour_images(tour_code);
CREATE INDEX IF NOT EXISTS idx_tour_images_type ON tour_images(image_type);

-- Initialize sync metadata
INSERT OR IGNORE INTO sync_metadata (key, value, updated_at)
VALUES ('last_sync', '1970-01-01T00:00:00Z', datetime('now'));

INSERT OR IGNORE INTO sync_metadata (key, value, updated_at)
VALUES ('sync_status', 'never_run', datetime('now'));
