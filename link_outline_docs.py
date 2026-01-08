#!/usr/bin/env python3
"""Link unsynced Outline docs to PostgreSQL tours by matching slugs."""

import json
import os
import psycopg2
import requests
from difflib import SequenceMatcher
from dotenv import load_dotenv

load_dotenv()

OUTLINE_API_URL = os.getenv('OUTLINE_API_URL')
OUTLINE_API_KEY = os.getenv('OUTLINE_API_KEY')

def outline_request(endpoint, data):
    headers = {
        'Authorization': f'Bearer {OUTLINE_API_KEY}',
        'Content-Type': 'application/json',
    }
    response = requests.post(f"{OUTLINE_API_URL}/{endpoint}", headers=headers, json=data)
    return response.json()

def main():
    # Load gaps
    with open('/tmp/outline_gaps.json') as f:
        gaps = json.load(f)

    # Connect to DB
    conn = psycopg2.connect(
        host='/var/run/postgresql',
        port='5433',
        database='rimtours',
        user='eric'
    )
    cur = conn.cursor()

    # Get all PG tours
    cur.execute("SELECT id, slug, title, outline_doc_id FROM tours WHERE slug IS NOT NULL")
    pg_tours = {row[1]: {'id': row[0], 'title': row[2], 'outline_doc_id': row[3]} for row in cur.fetchall()}

    outline_not_pg = gaps['in_outline_not_pg']

    print("LINKING OUTLINE DOCS TO POSTGRESQL TOURS")
    print("=" * 60)

    linked = 0
    not_linked = []

    for outline_slug, info in outline_not_pg.items():
        # Find best match
        best_match = None
        best_score = 0
        for pg_slug in pg_tours:
            score = SequenceMatcher(None, outline_slug.lower(), pg_slug.lower()).ratio()
            if score > best_score:
                best_score = score
                best_match = pg_slug

        if best_score >= 0.85:
            # Link this Outline doc to the PostgreSQL tour
            pg_tour = pg_tours[best_match]
            outline_doc_id = info['id']

            # Update PostgreSQL with the Outline doc ID
            cur.execute(
                "UPDATE tours SET outline_doc_id = %s WHERE id = %s",
                (outline_doc_id, pg_tour['id'])
            )

            print(f"✓ Linked: {outline_slug}")
            print(f"  → PG: {best_match} (score: {best_score:.2f})")
            linked += 1
        else:
            not_linked.append({
                'outline_slug': outline_slug,
                'outline_id': info['id'],
                'type': info['type'],
                'best_pg_match': best_match,
                'score': best_score
            })
            print(f"✗ Not linked: {outline_slug} (best: {best_match}, score: {best_score:.2f})")

    conn.commit()
    conn.close()

    print(f"\nLinked: {linked}")
    print(f"Not linked: {len(not_linked)}")

    # Save not linked for manual review
    with open('/tmp/not_linked.json', 'w') as f:
        json.dump(not_linked, f, indent=2)

    if not_linked:
        print("\nNot linked tours saved to /tmp/not_linked.json")

    return not_linked

if __name__ == "__main__":
    main()
