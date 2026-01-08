-- RimTours Unified Data Schema
-- PostgreSQL schema with field ownership tracking

-- ============================================
-- TOURS - Master table
-- ============================================
CREATE TABLE IF NOT EXISTS tours (
    id SERIAL PRIMARY KEY,

    -- Identity (from website)
    website_id VARCHAR(20),
    title VARCHAR(255) NOT NULL,
    slug VARCHAR(255),
    permalink TEXT,

    -- Classification
    tour_type VARCHAR(255),
    region VARCHAR(255),
    duration VARCHAR(100),
    season VARCHAR(100),
    style VARCHAR(255),
    skill_level VARCHAR(255),

    -- Content (editable in Outline)
    subtitle TEXT,
    short_description TEXT,
    description TEXT,
    special_notes TEXT,

    -- Logistics
    departs VARCHAR(255),
    distance VARCHAR(100),
    scheduled_dates TEXT,

    -- Itinerary metadata (from Word docs, editable in Outline)
    meeting_time VARCHAR(50),
    meeting_location TEXT,
    tour_rating TEXT,
    terrain TEXT,
    technical_difficulty TEXT,
    altitude VARCHAR(100),

    -- Booking
    reservation_link TEXT,

    -- Arctic linkage
    arctic_id VARCHAR(50),
    arctic_shortname VARCHAR(100),

    -- Field ownership tracking
    -- 'website' = initial import, 'outline' = editable, 'arctic' = read-only SSOT
    content_source VARCHAR(20) DEFAULT 'website',

    -- Sync tracking
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_outline_sync TIMESTAMP,
    last_arctic_sync TIMESTAMP,
    outline_doc_id VARCHAR(100),

    UNIQUE(website_id),
    UNIQUE(slug)
);

-- ============================================
-- TOUR PRICING - From Arctic (SSOT)
-- ============================================
CREATE TABLE IF NOT EXISTS tour_pricing (
    id SERIAL PRIMARY KEY,
    tour_id INTEGER REFERENCES tours(id) ON DELETE CASCADE,

    -- Pricing type
    pricing_type VARCHAR(50) NOT NULL, -- 'standard', 'private', 'solo', 'group_2plus', etc.
    variant VARCHAR(100), -- 'half_day', 'full_day', '4_day', etc.

    -- Amount
    amount DECIMAL(10,2),
    amount_display VARCHAR(100), -- formatted string like "$1,450"
    per_unit VARCHAR(50), -- 'pp', 'per person', 'per day', etc.

    -- Source tracking
    source VARCHAR(20) DEFAULT 'arctic', -- ALWAYS 'arctic' for pricing
    arctic_price_id VARCHAR(50),

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(tour_id, pricing_type, variant)
);

-- ============================================
-- TOUR RENTAL FEES - From website/Arctic
-- ============================================
CREATE TABLE IF NOT EXISTS tour_fees (
    id SERIAL PRIMARY KEY,
    tour_id INTEGER REFERENCES tours(id) ON DELETE CASCADE,

    fee_type VARCHAR(50) NOT NULL, -- 'bike_rental', 'camp_rental', 'shuttle'
    amount_display VARCHAR(100), -- "$80/day", "$95/person"

    source VARCHAR(20) DEFAULT 'website',

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(tour_id, fee_type)
);

-- ============================================
-- TOUR ITINERARY DAYS - Editable in Outline
-- ============================================
CREATE TABLE IF NOT EXISTS tour_itinerary_days (
    id SERIAL PRIMARY KEY,
    tour_id INTEGER REFERENCES tours(id) ON DELETE CASCADE,

    day_number INTEGER NOT NULL,

    -- Structured data
    miles VARCHAR(50),
    elevation VARCHAR(50),
    trails_waypoints TEXT,
    camp_lodging TEXT,
    meals TEXT,

    -- Full content
    content TEXT,

    -- Source tracking
    source VARCHAR(20) DEFAULT 'outline', -- editable in Outline

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(tour_id, day_number)
);

-- ============================================
-- TOUR IMAGES - From website
-- ============================================
CREATE TABLE IF NOT EXISTS tour_images (
    id SERIAL PRIMARY KEY,
    tour_id INTEGER REFERENCES tours(id) ON DELETE CASCADE,

    image_url TEXT NOT NULL,
    display_order INTEGER DEFAULT 0,
    alt_text TEXT,
    is_featured BOOLEAN DEFAULT FALSE,

    source VARCHAR(20) DEFAULT 'website',

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(tour_id, image_url)
);

-- ============================================
-- TOUR DATES - From Arctic (SSOT)
-- ============================================
CREATE TABLE IF NOT EXISTS tour_dates (
    id SERIAL PRIMARY KEY,
    tour_id INTEGER REFERENCES tours(id) ON DELETE CASCADE,

    start_date DATE NOT NULL,
    end_date DATE,

    -- Status from Arctic
    status VARCHAR(50) DEFAULT 'scheduled', -- 'scheduled', 'sold_out', 'cancelled'
    spots_available INTEGER,

    -- Source tracking
    source VARCHAR(20) DEFAULT 'arctic', -- ALWAYS 'arctic' for dates
    arctic_event_id VARCHAR(50),

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(tour_id, start_date)
);

-- ============================================
-- SYNC LOG - Track all sync operations
-- ============================================
CREATE TABLE IF NOT EXISTS sync_log (
    id SERIAL PRIMARY KEY,

    sync_type VARCHAR(50) NOT NULL, -- 'outline_push', 'outline_pull', 'arctic_sync', 'initial_load'
    tour_id INTEGER REFERENCES tours(id) ON DELETE SET NULL,

    status VARCHAR(20) NOT NULL, -- 'success', 'failed', 'partial'
    records_affected INTEGER DEFAULT 0,

    details JSONB, -- any additional info
    error_message TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- FIELD OWNERSHIP CONFIG - Defines which system owns which field
-- ============================================
CREATE TABLE IF NOT EXISTS field_ownership (
    id SERIAL PRIMARY KEY,

    table_name VARCHAR(100) NOT NULL,
    field_name VARCHAR(100) NOT NULL,

    owner VARCHAR(20) NOT NULL, -- 'arctic', 'outline', 'website'
    is_editable_in_outline BOOLEAN DEFAULT FALSE,

    description TEXT,

    UNIQUE(table_name, field_name)
);

-- Insert field ownership rules
INSERT INTO field_ownership (table_name, field_name, owner, is_editable_in_outline, description) VALUES
-- Tours table
('tours', 'title', 'outline', TRUE, 'Tour name - editable'),
('tours', 'subtitle', 'outline', TRUE, 'Tagline - editable'),
('tours', 'short_description', 'outline', TRUE, 'Brief description - editable'),
('tours', 'description', 'outline', TRUE, 'Full description - editable'),
('tours', 'special_notes', 'outline', TRUE, 'Additional notes - editable'),
('tours', 'tour_type', 'website', FALSE, 'Classification from website'),
('tours', 'region', 'website', FALSE, 'Geographic region'),
('tours', 'duration', 'website', FALSE, 'Trip length'),
('tours', 'season', 'website', FALSE, 'Operating seasons'),
('tours', 'meeting_time', 'outline', TRUE, 'Meeting time - editable'),
('tours', 'meeting_location', 'outline', TRUE, 'Meeting place - editable'),
('tours', 'tour_rating', 'outline', TRUE, 'Difficulty rating - editable'),
('tours', 'terrain', 'outline', TRUE, 'Terrain description - editable'),
('tours', 'technical_difficulty', 'outline', TRUE, 'Technical rating - editable'),
('tours', 'altitude', 'outline', TRUE, 'Elevation info - editable'),
-- Pricing - Arctic owned
('tour_pricing', 'amount', 'arctic', FALSE, 'Price from Arctic - DO NOT EDIT'),
('tour_pricing', 'amount_display', 'arctic', FALSE, 'Formatted price - DO NOT EDIT'),
-- Dates - Arctic owned
('tour_dates', 'start_date', 'arctic', FALSE, 'Tour date from Arctic - DO NOT EDIT'),
('tour_dates', 'status', 'arctic', FALSE, 'Availability from Arctic - DO NOT EDIT'),
-- Itinerary - Outline editable
('tour_itinerary_days', 'content', 'outline', TRUE, 'Day description - editable'),
('tour_itinerary_days', 'miles', 'outline', TRUE, 'Daily mileage - editable'),
('tour_itinerary_days', 'elevation', 'outline', TRUE, 'Daily elevation - editable')
ON CONFLICT (table_name, field_name) DO NOTHING;

-- ============================================
-- INDEXES for performance
-- ============================================
CREATE INDEX IF NOT EXISTS idx_tours_slug ON tours(slug);
CREATE INDEX IF NOT EXISTS idx_tours_website_id ON tours(website_id);
CREATE INDEX IF NOT EXISTS idx_tours_arctic_id ON tours(arctic_id);
CREATE INDEX IF NOT EXISTS idx_tours_outline_doc_id ON tours(outline_doc_id);
CREATE INDEX IF NOT EXISTS idx_tour_pricing_tour_id ON tour_pricing(tour_id);
CREATE INDEX IF NOT EXISTS idx_tour_itinerary_tour_id ON tour_itinerary_days(tour_id);
CREATE INDEX IF NOT EXISTS idx_tour_images_tour_id ON tour_images(tour_id);
CREATE INDEX IF NOT EXISTS idx_tour_dates_tour_id ON tour_dates(tour_id);
CREATE INDEX IF NOT EXISTS idx_tour_dates_start ON tour_dates(start_date);
CREATE INDEX IF NOT EXISTS idx_sync_log_type ON sync_log(sync_type);
CREATE INDEX IF NOT EXISTS idx_sync_log_tour ON sync_log(tour_id);

-- ============================================
-- UPDATED_AT trigger function
-- ============================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply trigger to tables
DROP TRIGGER IF EXISTS update_tours_updated_at ON tours;
CREATE TRIGGER update_tours_updated_at
    BEFORE UPDATE ON tours
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_tour_pricing_updated_at ON tour_pricing;
CREATE TRIGGER update_tour_pricing_updated_at
    BEFORE UPDATE ON tour_pricing
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_tour_fees_updated_at ON tour_fees;
CREATE TRIGGER update_tour_fees_updated_at
    BEFORE UPDATE ON tour_fees
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_tour_itinerary_days_updated_at ON tour_itinerary_days;
CREATE TRIGGER update_tour_itinerary_days_updated_at
    BEFORE UPDATE ON tour_itinerary_days
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_tour_dates_updated_at ON tour_dates;
CREATE TRIGGER update_tour_dates_updated_at
    BEFORE UPDATE ON tour_dates
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
