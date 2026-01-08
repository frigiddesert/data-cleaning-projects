#!/usr/bin/env python3
"""
Load unified tour data into PostgreSQL

Loads data from unified_tours.json into the PostgreSQL database,
respecting field ownership rules.
"""

import json
import os
import re
import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Database connection settings
_host = os.getenv('POSTGRES_HOST', 'localhost')
DB_CONFIG = {
    'database': os.getenv('POSTGRES_DB', 'rimtours'),
    'user': os.getenv('POSTGRES_USER', 'postgres'),
    'port': os.getenv('POSTGRES_PORT', '5432'),
}
# Use Unix socket for local peer auth, otherwise use host
if _host == 'localhost' and not os.getenv('POSTGRES_PASSWORD'):
    DB_CONFIG['host'] = '/var/run/postgresql'  # Unix socket
else:
    DB_CONFIG['host'] = _host
    DB_CONFIG['password'] = os.getenv('POSTGRES_PASSWORD', '')

INPUT_FILE = 'unified_tours.json'


def get_connection():
    """Create database connection."""
    return psycopg2.connect(**DB_CONFIG)


def parse_price_amount(price_str):
    """Extract numeric amount from price string like '$1,450' or '$80/day'."""
    if not price_str:
        return None
    match = re.search(r'\$([0-9,]+)', price_str)
    if match:
        return float(match.group(1).replace(',', ''))
    return None


def load_tours(conn, tours):
    """Load tours into the tours table."""
    cur = conn.cursor()

    inserted = 0
    updated = 0

    for tour in tours:
        # Extract meeting location parts
        meeting_time = ''
        meeting_loc = ''
        if tour.get('meeting_location'):
            if isinstance(tour['meeting_location'], dict):
                meeting_time = tour['meeting_location'].get('time', '')
                meeting_loc = tour['meeting_location'].get('location', '')
            else:
                meeting_loc = str(tour['meeting_location'])

        # Check if tour exists
        cur.execute("SELECT id FROM tours WHERE website_id = %s", (tour.get('website_id'),))
        existing = cur.fetchone()

        if existing:
            # Update existing tour
            cur.execute("""
                UPDATE tours SET
                    title = %s,
                    slug = %s,
                    permalink = %s,
                    tour_type = %s,
                    region = %s,
                    duration = %s,
                    season = %s,
                    style = %s,
                    skill_level = %s,
                    subtitle = %s,
                    short_description = %s,
                    description = %s,
                    special_notes = %s,
                    departs = %s,
                    distance = %s,
                    scheduled_dates = %s,
                    meeting_time = %s,
                    meeting_location = %s,
                    tour_rating = %s,
                    terrain = %s,
                    technical_difficulty = %s,
                    altitude = %s,
                    reservation_link = %s,
                    content_source = 'website'
                WHERE website_id = %s
                RETURNING id
            """, (
                tour.get('title'),
                tour.get('slug'),
                tour.get('permalink'),
                tour.get('tour_type'),
                tour.get('region'),
                tour.get('duration'),
                tour.get('season'),
                tour.get('style'),
                tour.get('skill_level'),
                tour.get('subtitle'),
                tour.get('short_description'),
                tour.get('description'),
                tour.get('special_notes'),
                tour.get('departs'),
                tour.get('distance'),
                tour.get('scheduled_dates'),
                meeting_time,
                meeting_loc,
                tour.get('tour_rating'),
                tour.get('terrain'),
                tour.get('technical_difficulty'),
                tour.get('altitude'),
                tour.get('reservation_link'),
                tour.get('website_id'),
            ))
            tour_id = cur.fetchone()[0]
            updated += 1
        else:
            # Insert new tour
            cur.execute("""
                INSERT INTO tours (
                    website_id, title, slug, permalink,
                    tour_type, region, duration, season, style, skill_level,
                    subtitle, short_description, description, special_notes,
                    departs, distance, scheduled_dates,
                    meeting_time, meeting_location,
                    tour_rating, terrain, technical_difficulty, altitude,
                    reservation_link, content_source
                ) VALUES (
                    %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s,
                    %s, %s, %s, %s,
                    %s, 'website'
                )
                RETURNING id
            """, (
                tour.get('website_id'),
                tour.get('title'),
                tour.get('slug'),
                tour.get('permalink'),
                tour.get('tour_type'),
                tour.get('region'),
                tour.get('duration'),
                tour.get('season'),
                tour.get('style'),
                tour.get('skill_level'),
                tour.get('subtitle'),
                tour.get('short_description'),
                tour.get('description'),
                tour.get('special_notes'),
                tour.get('departs'),
                tour.get('distance'),
                tour.get('scheduled_dates'),
                meeting_time,
                meeting_loc,
                tour.get('tour_rating'),
                tour.get('terrain'),
                tour.get('technical_difficulty'),
                tour.get('altitude'),
                tour.get('reservation_link'),
            ))
            tour_id = cur.fetchone()[0]
            inserted += 1

        # Store tour_id for related tables
        tour['_db_id'] = tour_id

    conn.commit()
    return inserted, updated


def load_fees(conn, tours):
    """Load tour fees (bike rental, camp rental, etc.)."""
    cur = conn.cursor()
    count = 0

    for tour in tours:
        tour_id = tour.get('_db_id')
        if not tour_id:
            continue

        pricing = tour.get('pricing', {})

        # Delete existing fees for this tour
        cur.execute("DELETE FROM tour_fees WHERE tour_id = %s", (tour_id,))

        fees = [
            ('bike_rental', pricing.get('bike_rental')),
            ('camp_rental', pricing.get('camp_rental')),
        ]

        for fee_type, amount_display in fees:
            if amount_display:
                cur.execute("""
                    INSERT INTO tour_fees (tour_id, fee_type, amount_display, source)
                    VALUES (%s, %s, %s, 'website')
                    ON CONFLICT (tour_id, fee_type) DO UPDATE SET amount_display = EXCLUDED.amount_display
                """, (tour_id, fee_type, amount_display))
                count += 1

        # Also store standard/private pricing temporarily (until Arctic sync)
        if pricing.get('standard'):
            cur.execute("""
                INSERT INTO tour_pricing (tour_id, pricing_type, variant, amount_display, source)
                VALUES (%s, 'standard', 'default', %s, 'website')
                ON CONFLICT (tour_id, pricing_type, variant) DO UPDATE SET amount_display = EXCLUDED.amount_display
            """, (tour_id, pricing.get('standard')))

        if pricing.get('private'):
            cur.execute("""
                INSERT INTO tour_pricing (tour_id, pricing_type, variant, amount_display, source)
                VALUES (%s, 'private', 'default', %s, 'website')
                ON CONFLICT (tour_id, pricing_type, variant) DO UPDATE SET amount_display = EXCLUDED.amount_display
            """, (tour_id, pricing.get('private')))

    conn.commit()
    return count


def load_itinerary_days(conn, tours):
    """Load itinerary days."""
    cur = conn.cursor()
    count = 0

    for tour in tours:
        tour_id = tour.get('_db_id')
        if not tour_id:
            continue

        days = tour.get('itinerary_days', [])
        if not days:
            continue

        # Delete existing days for this tour
        cur.execute("DELETE FROM tour_itinerary_days WHERE tour_id = %s", (tour_id,))

        for day in days:
            day_num = day.get('day')
            if not day_num:
                continue

            try:
                day_num = int(day_num)
            except (ValueError, TypeError):
                continue

            cur.execute("""
                INSERT INTO tour_itinerary_days (
                    tour_id, day_number, miles, elevation,
                    trails_waypoints, camp_lodging, meals, content, source
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'outline')
            """, (
                tour_id,
                day_num,
                day.get('miles'),
                day.get('elevation'),
                day.get('trails_waypoints'),
                day.get('camp_lodging'),
                day.get('meals'),
                day.get('content'),
            ))
            count += 1

    conn.commit()
    return count


def load_images(conn, tours):
    """Load tour images."""
    cur = conn.cursor()
    count = 0

    for tour in tours:
        tour_id = tour.get('_db_id')
        if not tour_id:
            continue

        images = tour.get('images', [])
        if not images:
            continue

        # Delete existing images for this tour
        cur.execute("DELETE FROM tour_images WHERE tour_id = %s", (tour_id,))

        for i, img_url in enumerate(images):
            cur.execute("""
                INSERT INTO tour_images (tour_id, image_url, display_order, is_featured, source)
                VALUES (%s, %s, %s, %s, 'website')
                ON CONFLICT (tour_id, image_url) DO NOTHING
            """, (tour_id, img_url, i, i == 0))
            count += 1

    conn.commit()
    return count


def log_sync(conn, sync_type, records_affected, status='success', details=None):
    """Log a sync operation."""
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO sync_log (sync_type, status, records_affected, details)
        VALUES (%s, %s, %s, %s)
    """, (sync_type, status, records_affected, json.dumps(details) if details else None))
    conn.commit()


def main():
    print("=" * 60)
    print("LOADING TOUR DATA INTO POSTGRESQL")
    print("=" * 60)

    # Load JSON data
    print(f"\nLoading data from {INPUT_FILE}...")
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    tours = data.get('tours', [])
    print(f"  Found {len(tours)} tours")

    # Connect to database
    print(f"\nConnecting to PostgreSQL...")
    print(f"  Host: {DB_CONFIG['host']}")
    print(f"  Database: {DB_CONFIG['database']}")

    try:
        conn = get_connection()
        print("  Connected!")
    except Exception as e:
        print(f"  ERROR: Could not connect to database: {e}")
        print("\n  Make sure PostgreSQL is running and credentials are set in .env:")
        print("    POSTGRES_HOST=localhost")
        print("    POSTGRES_PORT=5432")
        print("    POSTGRES_DB=rimtours")
        print("    POSTGRES_USER=postgres")
        print("    POSTGRES_PASSWORD=yourpassword")
        return

    try:
        # Load data
        print("\nLoading tours...")
        inserted, updated = load_tours(conn, tours)
        print(f"  Inserted: {inserted}, Updated: {updated}")

        print("\nLoading fees...")
        fees_count = load_fees(conn, tours)
        print(f"  Loaded: {fees_count} fee records")

        print("\nLoading itinerary days...")
        days_count = load_itinerary_days(conn, tours)
        print(f"  Loaded: {days_count} itinerary days")

        print("\nLoading images...")
        images_count = load_images(conn, tours)
        print(f"  Loaded: {images_count} images")

        # Log the sync
        log_sync(conn, 'initial_load', inserted + updated, details={
            'tours_inserted': inserted,
            'tours_updated': updated,
            'fees': fees_count,
            'itinerary_days': days_count,
            'images': images_count,
        })

        print("\n" + "=" * 60)
        print("LOAD COMPLETE")
        print("=" * 60)

    except Exception as e:
        print(f"\nERROR: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
