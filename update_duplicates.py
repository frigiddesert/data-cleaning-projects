#!/usr/bin/env python3
"""Update duplicate Outline docs with proper headers from their matching PostgreSQL tours."""

import os
import psycopg2
import requests
from dotenv import load_dotenv
from outline_sync import generate_reference_header, get_tour_pricing, get_tour_fees, get_tour_itinerary, strip_existing_header

load_dotenv()

OUTLINE_API_URL = os.getenv('OUTLINE_API_URL')
OUTLINE_API_KEY = os.getenv('OUTLINE_API_KEY')
COLLECTION_ID = os.getenv('OUTLINE_COLLECTION_ID')
DAY = os.getenv('OUTLINE_DAY_TOURS_DOC_ID')
MD = os.getenv('OUTLINE_MD_TOURS_DOC_ID')

# Mapping: Outline slug variant -> PostgreSQL slug
SLUG_MAP = {
    "arizona's-sonoran-desert": "arizonas-sonoran-desert",
    "bears-ears-backcountry-4-day": "bears-ears-backcountry-tour-4-day",
    "bears-ears-mnt.-bike-weekend-3-day": "bears-ears-mnt-bike-weekend-3-day",
    "best-of-crested-butte-ebike-tour": "best-of-crested-butte-inn-tour-ebike",
    "best-of-fruita-mountain-bike-inn-tour": "best-of-fruita-mountain-bike-tour",
    "best-of-moab-mnt.-bike-inn-tour": "best-moab-mountain-bike-tour",
    "custom-bnb-based-ebike-tour": "custom-bnb-based-tour",
    "dead-horse-point-ebike-singletrack": "dead-horse-point-singletrack",
    "grand-canyon-north-rim-4-day": "grand-canyon-north-rim-5-day",
}

def outline_request(endpoint, data):
    headers = {'Authorization': f'Bearer {OUTLINE_API_KEY}', 'Content-Type': 'application/json'}
    return requests.post(f"{OUTLINE_API_URL}/{endpoint}", headers=headers, json=data).json()

def main():
    # Get outline docs
    result = outline_request('documents.list', {'collectionId': COLLECTION_ID, 'limit': 100})
    outline_docs = {}
    for doc in result.get('data', []):
        if doc.get('parentDocumentId') in [DAY, MD]:
            outline_docs[doc['title']] = doc['id']

    conn = psycopg2.connect(host='/var/run/postgresql', port='5433', database='rimtours', user='eric')
    cur = conn.cursor()

    print("UPDATING DUPLICATE OUTLINE DOCS WITH HEADERS")
    print("=" * 60)

    updated = 0
    for outline_slug, pg_slug in SLUG_MAP.items():
        if outline_slug not in outline_docs:
            print(f"  ? {outline_slug} - not in Outline")
            continue

        outline_doc_id = outline_docs[outline_slug]

        # Get PostgreSQL tour data
        cur.execute("""
            SELECT id, website_id, title, slug, permalink, tour_type, region, duration,
                   season, style, skill_level, subtitle, short_description, description,
                   special_notes, departs, distance, scheduled_dates, meeting_time,
                   meeting_location, tour_rating, terrain, technical_difficulty, altitude,
                   reservation_link, outline_doc_id, arctic_id, arctic_shortname
            FROM tours WHERE slug = %s
        """, (pg_slug,))
        row = cur.fetchone()
        if not row:
            print(f"  ? {pg_slug} - not in PostgreSQL")
            continue

        cols = ['id', 'website_id', 'title', 'slug', 'permalink', 'tour_type', 'region',
                'duration', 'season', 'style', 'skill_level', 'subtitle', 'short_description',
                'description', 'special_notes', 'departs', 'distance', 'scheduled_dates',
                'meeting_time', 'meeting_location', 'tour_rating', 'terrain',
                'technical_difficulty', 'altitude', 'reservation_link', 'outline_doc_id',
                'arctic_id', 'arctic_shortname']
        tour = dict(zip(cols, row))

        # Get related data
        pricing = get_tour_pricing(conn, tour['id'])
        fees = get_tour_fees(conn, tour['id'])
        itinerary = get_tour_itinerary(conn, tour['id'])

        # Get existing Outline content
        doc_result = outline_request('documents.info', {'id': outline_doc_id})
        existing_text = doc_result.get('data', {}).get('text', '')

        # Check if already has markers
        if '## ✏️ Editable Content' in existing_text:
            print(f"  - {outline_slug} (already has markers)")
            continue

        # Strip old header if any
        legacy = strip_existing_header(existing_text)

        # Generate new header
        header = generate_reference_header(tour, pricing, fees, itinerary)

        # Combine
        new_text = header + "\n" + legacy if legacy else header

        # Update
        outline_request('documents.update', {'id': outline_doc_id, 'text': new_text})
        print(f"  ~ {outline_slug}")
        updated += 1

    conn.close()
    print(f"\nUpdated {updated} duplicate docs")

if __name__ == "__main__":
    main()
