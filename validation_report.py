#!/usr/bin/env python3
"""Generate validation report for tours with missing fields."""

import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

conn = psycopg2.connect(
    host='/var/run/postgresql',
    port='5433',
    database='rimtours',
    user='eric'
)
cur = conn.cursor()

# Get all tours with their outline doc IDs
cur.execute("""
    SELECT t.id, t.slug, t.title, t.tour_type, t.outline_doc_id,
           t.description, t.short_description, t.subtitle,
           t.duration, t.skill_level, t.region, t.season,
           t.departs, t.meeting_location, t.meeting_time,
           t.distance, t.terrain, t.altitude,
           (SELECT COUNT(*) FROM tour_pricing tp WHERE tp.tour_id = t.id) as pricing_count,
           (SELECT COUNT(*) FROM tour_itinerary_days ti WHERE ti.tour_id = t.id) as itinerary_count,
           (SELECT COUNT(*) FROM tour_fees tf WHERE tf.tour_id = t.id) as fees_count
    FROM tours t
    ORDER BY t.tour_type, t.title
""")

tours = cur.fetchall()
cols = ['id', 'slug', 'title', 'tour_type', 'outline_doc_id',
        'description', 'short_description', 'subtitle',
        'duration', 'skill_level', 'region', 'season',
        'departs', 'meeting_location', 'meeting_time',
        'distance', 'terrain', 'altitude',
        'pricing_count', 'itinerary_count', 'fees_count']

OUTLINE_BASE = "https://outline.sandland.us/doc"

issues = {
    'no_description': [],
    'no_pricing': [],
    'no_duration': [],
    'no_skill_level': [],
    'no_meeting_info': [],
    'no_itinerary_multiday': [],
}

for row in tours:
    tour = dict(zip(cols, row))
    slug = tour['slug'] or 'unknown'
    title = tour['title'] or slug
    doc_id = tour['outline_doc_id']
    link = f"{OUTLINE_BASE}/{slug}-{doc_id[:8]}" if doc_id else "NO LINK"
    tour_type = tour['tour_type'] or 'Unknown'

    entry = {
        'title': title,
        'slug': slug,
        'type': tour_type,
        'link': link
    }

    # Check for missing fields
    if not tour['description'] and not tour['short_description']:
        issues['no_description'].append(entry)

    if tour['pricing_count'] == 0:
        issues['no_pricing'].append(entry)

    if not tour['duration']:
        issues['no_duration'].append(entry)

    if not tour['skill_level']:
        issues['no_skill_level'].append(entry)

    if not tour['meeting_location'] and not tour['meeting_time'] and not tour['departs']:
        issues['no_meeting_info'].append(entry)

    # Multi-day tours should have itinerary
    if 'Multi' in (tour_type or '') and tour['itinerary_count'] == 0:
        issues['no_itinerary_multiday'].append(entry)

print("# Tour Validation Report\n")
print(f"**Total Tours:** {len(tours)}\n")

print("## Missing Description")
print(f"*{len(issues['no_description'])} tours*\n")
for t in issues['no_description']:
    print(f"- [{t['title']}]({t['link']}) ({t['type']})")

print("\n## Missing Pricing")
print(f"*{len(issues['no_pricing'])} tours*\n")
for t in issues['no_pricing']:
    print(f"- [{t['title']}]({t['link']}) ({t['type']})")

print("\n## Missing Duration")
print(f"*{len(issues['no_duration'])} tours*\n")
for t in issues['no_duration']:
    print(f"- [{t['title']}]({t['link']}) ({t['type']})")

print("\n## Missing Skill Level")
print(f"*{len(issues['no_skill_level'])} tours*\n")
for t in issues['no_skill_level']:
    print(f"- [{t['title']}]({t['link']}) ({t['type']})")

print("\n## Missing Meeting Info")
print(f"*{len(issues['no_meeting_info'])} tours*\n")
for t in issues['no_meeting_info']:
    print(f"- [{t['title']}]({t['link']}) ({t['type']})")

print("\n## Multi-Day Tours Missing Itinerary")
print(f"*{len(issues['no_itinerary_multiday'])} tours*\n")
for t in issues['no_itinerary_multiday']:
    print(f"- [{t['title']}]({t['link']}) ({t['type']})")

conn.close()
