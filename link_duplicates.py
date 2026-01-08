#!/usr/bin/env python3
"""Link duplicate Outline docs (variant slugs) to existing PostgreSQL tours."""

import os
import psycopg2
import requests
from dotenv import load_dotenv

load_dotenv()

OUTLINE_API_URL = os.getenv('OUTLINE_API_URL')
OUTLINE_API_KEY = os.getenv('OUTLINE_API_KEY')

# Mapping: outline_slug -> postgresql_slug
SLUG_MAPPING = {
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
    headers = {
        'Authorization': f'Bearer {OUTLINE_API_KEY}',
        'Content-Type': 'application/json',
    }
    response = requests.post(f"{OUTLINE_API_URL}/{endpoint}", headers=headers, json=data)
    return response.json()

def main():
    # Get Outline docs
    result = outline_request('documents.list', {
        'collectionId': os.getenv('OUTLINE_COLLECTION_ID'),
        'limit': 100
    })

    outline_docs = {}
    DAY = os.getenv('OUTLINE_DAY_TOURS_DOC_ID')
    MD = os.getenv('OUTLINE_MD_TOURS_DOC_ID')

    for doc in result.get('data', []):
        if doc.get('parentDocumentId') in [DAY, MD]:
            outline_docs[doc['title']] = doc['id']

    conn = psycopg2.connect(
        host='/var/run/postgresql',
        port='5433',
        database='rimtours',
        user='eric'
    )
    cur = conn.cursor()

    print("LINKING DUPLICATE OUTLINE DOCS")
    print("=" * 60)

    for outline_slug, pg_slug in SLUG_MAPPING.items():
        if outline_slug not in outline_docs:
            print(f"  ? {outline_slug} - not found in Outline")
            continue

        outline_doc_id = outline_docs[outline_slug]

        # Get the PostgreSQL tour
        cur.execute("SELECT id, title, outline_doc_id FROM tours WHERE slug = %s", (pg_slug,))
        row = cur.fetchone()

        if not row:
            print(f"  ? {pg_slug} - not found in PostgreSQL")
            continue

        tour_id, title, existing_doc_id = row

        print(f"  {outline_slug}")
        print(f"    → PostgreSQL: {pg_slug}")
        print(f"    → Existing Outline ID: {existing_doc_id[:12] if existing_doc_id else 'None'}...")
        print(f"    → Duplicate Outline ID: {outline_doc_id[:12]}...")

        # We won't change the PostgreSQL link, but we'll update the duplicate Outline doc
        # with the same content structure

    conn.close()

    print("\nThese duplicate Outline docs exist alongside the linked versions.")
    print("You may want to delete them or merge their content.")

if __name__ == "__main__":
    main()
