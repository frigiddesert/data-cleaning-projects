#!/usr/bin/env python3
"""Create PostgreSQL records from unlinked Outline docs."""

import json
import os
import psycopg2
import requests
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
    # Load not linked
    with open('/tmp/not_linked.json') as f:
        not_linked = json.load(f)

    print("FETCHING OUTLINE CONTENT FOR UNLINKED DOCS")
    print("=" * 60)

    tours_to_create = []

    for item in not_linked:
        slug = item['outline_slug']
        doc_id = item['outline_id']
        tour_type = item['type']

        # Fetch doc content
        result = outline_request('documents.info', {'id': doc_id})
        doc = result.get('data', {})

        title = doc.get('title', slug)
        text = doc.get('text', '')

        # Extract description from first meaningful paragraph
        lines = text.split('\n')
        description = ''
        for line in lines:
            line = line.strip()
            if line and not line.startswith('#') and not line.startswith('|') and not line.startswith('>') and not line.startswith('*') and not line.startswith('-') and len(line) > 20:
                description = line[:500]
                break

        # Make title human readable
        display_title = title
        if title == slug or '-' in title:
            display_title = title.replace('-', ' ').replace('.', '').title()

        print(f"\n{slug}")
        print(f"  Title: {display_title}")
        print(f"  Type: {tour_type}")
        print(f"  Content length: {len(text)} chars")
        if description:
            print(f"  Description: {description[:80]}...")

        tours_to_create.append({
            'slug': slug.replace('.', ''),
            'title': display_title,
            'tour_type': 'Day Tours' if tour_type == 'day' else 'Multi-Day Tours',
            'outline_doc_id': doc_id,
            'description': description,
            'is_day_tour': tour_type == 'day'
        })

    # Create in PostgreSQL
    print("\n" + "=" * 60)
    print("CREATING IN POSTGRESQL")
    print("=" * 60)

    conn = psycopg2.connect(
        host='/var/run/postgresql',
        port='5433',
        database='rimtours',
        user='eric'
    )
    cur = conn.cursor()

    created = 0
    for tour in tours_to_create:
        # Check if already exists
        cur.execute("SELECT id FROM tours WHERE slug = %s", (tour['slug'],))
        if cur.fetchone():
            print(f"  - {tour['slug']} already exists, skipping")
            continue

        cur.execute("""
            INSERT INTO tours (slug, title, tour_type, outline_doc_id, description, content_source)
            VALUES (%s, %s, %s, %s, %s, 'outline')
            RETURNING id
        """, (tour['slug'], tour['title'], tour['tour_type'], tour['outline_doc_id'], tour['description']))

        tour_id = cur.fetchone()[0]
        print(f"  + Created: {tour['slug']} (ID: {tour_id})")
        created += 1

    conn.commit()
    conn.close()

    print(f"\nCreated {created} new tours in PostgreSQL")
    return created

if __name__ == "__main__":
    main()
