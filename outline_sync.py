#!/usr/bin/env python3
"""
Outline Document Sync

Bidirectional sync between PostgreSQL and Outline:
- Push: Generate Outline documents from PostgreSQL data
- Pull: Update PostgreSQL from edited Outline documents

Respects field ownership:
- 'outline' fields: Editable in Outline, synced back to PostgreSQL
- 'arctic' fields: Read-only display, never modified from Outline
- 'website' fields: Read-only display, classification data
"""

import json
import os
import re
import requests
import psycopg2
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Outline API Configuration
OUTLINE_API_URL = os.getenv('OUTLINE_API_URL', 'https://app.getoutline.com/api')
OUTLINE_API_KEY = os.getenv('OUTLINE_API_KEY', '')
OUTLINE_COLLECTION_ID = os.getenv('OUTLINE_COLLECTION_ID', '')
OUTLINE_DAY_TOURS_DOC_ID = os.getenv('OUTLINE_DAY_TOURS_DOC_ID', '')
OUTLINE_MD_TOURS_DOC_ID = os.getenv('OUTLINE_MD_TOURS_DOC_ID', '')

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

# Field ownership - defines what can be edited in Outline
EDITABLE_FIELDS = {
    'title', 'subtitle', 'short_description', 'description', 'special_notes',
    'meeting_time', 'meeting_location', 'tour_rating', 'terrain',
    'technical_difficulty', 'altitude',
}

READONLY_FIELDS = {
    'website_id', 'slug', 'permalink', 'tour_type', 'region', 'duration',
    'season', 'style', 'skill_level', 'departs', 'distance',
}

# ==========================================
# DATABASE FUNCTIONS
# ==========================================

def get_db_connection():
    """Create database connection."""
    return psycopg2.connect(**DB_CONFIG)


def get_tours_from_db(conn):
    """Fetch all tours from PostgreSQL."""
    cur = conn.cursor()
    cur.execute("""
        SELECT
            t.id, t.website_id, t.title, t.slug, t.permalink,
            t.tour_type, t.region, t.duration, t.season, t.style, t.skill_level,
            t.subtitle, t.short_description, t.description, t.special_notes,
            t.departs, t.distance, t.scheduled_dates,
            t.meeting_time, t.meeting_location,
            t.tour_rating, t.terrain, t.technical_difficulty, t.altitude,
            t.reservation_link, t.outline_doc_id,
            t.arctic_id, t.arctic_shortname
        FROM tours t
        ORDER BY t.title
    """)

    columns = [desc[0] for desc in cur.description]
    tours = []
    for row in cur.fetchall():
        tours.append(dict(zip(columns, row)))

    return tours


def get_tour_itinerary(conn, tour_id):
    """Get itinerary days for a tour."""
    cur = conn.cursor()
    cur.execute("""
        SELECT day_number, miles, elevation, trails_waypoints,
               camp_lodging, meals, content
        FROM tour_itinerary_days
        WHERE tour_id = %s
        ORDER BY day_number
    """, (tour_id,))

    columns = [desc[0] for desc in cur.description]
    days = []
    for row in cur.fetchall():
        days.append(dict(zip(columns, row)))

    return days


def get_tour_pricing(conn, tour_id):
    """Get pricing for a tour."""
    cur = conn.cursor()
    cur.execute("""
        SELECT pricing_type, variant, amount_display
        FROM tour_pricing
        WHERE tour_id = %s
        ORDER BY pricing_type, variant
    """, (tour_id,))

    return cur.fetchall()


def get_tour_fees(conn, tour_id):
    """Get fees for a tour."""
    cur = conn.cursor()
    cur.execute("""
        SELECT fee_type, amount_display
        FROM tour_fees
        WHERE tour_id = %s
        ORDER BY fee_type
    """, (tour_id,))

    return cur.fetchall()


def update_tour_outline_doc_id(conn, tour_id, doc_id):
    """Update the outline_doc_id for a tour."""
    cur = conn.cursor()
    cur.execute("""
        UPDATE tours
        SET outline_doc_id = %s, last_outline_sync = CURRENT_TIMESTAMP
        WHERE id = %s
    """, (doc_id, tour_id))
    conn.commit()


def update_tour_from_outline(conn, tour_id, updates):
    """Update tour fields from Outline (only editable fields)."""
    cur = conn.cursor()

    # Filter to only editable fields
    safe_updates = {k: v for k, v in updates.items() if k in EDITABLE_FIELDS}

    if not safe_updates:
        return 0

    # Build UPDATE query
    set_clauses = [f"{field} = %s" for field in safe_updates.keys()]
    values = list(safe_updates.values()) + [tour_id]

    cur.execute(f"""
        UPDATE tours
        SET {', '.join(set_clauses)}, last_outline_sync = CURRENT_TIMESTAMP
        WHERE id = %s
    """, values)

    conn.commit()
    return cur.rowcount


def update_itinerary_from_outline(conn, tour_id, days):
    """Update itinerary days from Outline."""
    cur = conn.cursor()
    count = 0

    for day in days:
        day_num = day.get('day_number')
        if not day_num:
            continue

        cur.execute("""
            INSERT INTO tour_itinerary_days (
                tour_id, day_number, miles, elevation,
                trails_waypoints, camp_lodging, meals, content, source
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'outline')
            ON CONFLICT (tour_id, day_number) DO UPDATE SET
                miles = EXCLUDED.miles,
                elevation = EXCLUDED.elevation,
                trails_waypoints = EXCLUDED.trails_waypoints,
                camp_lodging = EXCLUDED.camp_lodging,
                meals = EXCLUDED.meals,
                content = EXCLUDED.content,
                source = 'outline',
                updated_at = CURRENT_TIMESTAMP
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


def log_sync(conn, sync_type, tour_id, status='success', details=None, error=None):
    """Log a sync operation."""
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO sync_log (sync_type, tour_id, status, records_affected, details, error_message)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (
        sync_type,
        tour_id,
        status,
        1 if status == 'success' else 0,
        json.dumps(details) if details else None,
        error
    ))
    conn.commit()


# ==========================================
# OUTLINE API FUNCTIONS
# ==========================================

def outline_request(endpoint, data=None):
    """Make a request to Outline API."""
    headers = {
        'Authorization': f'Bearer {OUTLINE_API_KEY}',
        'Content-Type': 'application/json',
    }

    url = f"{OUTLINE_API_URL}/{endpoint}"

    if data:
        response = requests.post(url, headers=headers, json=data)
    else:
        response = requests.post(url, headers=headers)

    if response.status_code != 200:
        raise Exception(f"Outline API error: {response.status_code} - {response.text}")

    return response.json()


def get_outline_document(doc_id):
    """Fetch a document from Outline."""
    result = outline_request('documents.info', {'id': doc_id})
    return result.get('data')


def create_outline_document(title, text, collection_id, parent_doc_id=None):
    """Create a new document in Outline."""
    data = {
        'title': title,
        'text': text,
        'collectionId': collection_id,
        'publish': True,
    }
    if parent_doc_id:
        data['parentDocumentId'] = parent_doc_id

    result = outline_request('documents.create', data)
    return result.get('data')


def update_outline_document(doc_id, title=None, text=None):
    """Update an existing document in Outline."""
    data = {'id': doc_id}
    if title:
        data['title'] = title
    if text:
        data['text'] = text

    result = outline_request('documents.update', data)
    return result.get('data')


def search_outline_documents(query, collection_id=None):
    """Search for documents in Outline."""
    data = {'query': query}
    if collection_id:
        data['collectionId'] = collection_id

    result = outline_request('documents.search', data)
    return result.get('data', [])


def get_existing_tour_docs():
    """Get all existing tour documents under Day Tours and Multi-Day parents."""
    result = outline_request('documents.list', {
        'collectionId': OUTLINE_COLLECTION_ID,
        'limit': 100
    })

    docs_by_slug = {}
    for doc in result.get('data', []):
        parent = doc.get('parentDocumentId')
        # Only include docs under Day Tours or Multi-Day
        if parent in [OUTLINE_DAY_TOURS_DOC_ID, OUTLINE_MD_TOURS_DOC_ID]:
            # Use title as slug (docs are named by slug)
            slug = doc['title']
            docs_by_slug[slug] = {
                'id': doc['id'],
                'title': doc['title'],
                'parent': 'day' if parent == OUTLINE_DAY_TOURS_DOC_ID else 'multi-day'
            }
    return docs_by_slug


def is_day_tour(tour):
    """Determine if a tour is a day tour based on tour_type."""
    tour_type = (tour.get('tour_type') or '').lower()
    # Day tours have "day" in type but not "multi-day"
    if 'multi-day' in tour_type or 'multi day' in tour_type:
        return False
    if 'day tour' in tour_type or 'day-tour' in tour_type:
        return True
    # Check duration - anything 1 day is a day tour
    duration = (tour.get('duration') or '').lower()
    if 'half' in duration or 'full day' in duration or duration in ['1 day', '1-day']:
        return True
    # Default to multi-day if unclear
    return False


# ==========================================
# DOCUMENT GENERATION
# ==========================================

def generate_reference_header(tour, pricing, fees, itinerary_days=None):
    """Generate the reference header with editable field markers."""
    lines = []

    # Reference IDs section (read-only)
    lines.append("---")
    lines.append("## 🔗 Reference IDs")
    lines.append("> Cross-system identifiers for this tour.")
    lines.append("")
    lines.append("| System | Identifier |")
    lines.append("|--------|------------|")
    lines.append(f"| **Title** | {tour['title']} |")
    if tour.get('slug'):
        lines.append(f"| **Slug** | `{tour['slug']}` |")
    if tour.get('website_id'):
        lines.append(f"| **Website ID** | {tour['website_id']} |")
    if tour.get('arctic_shortname'):
        lines.append(f"| **Arctic Shortname** | `{tour['arctic_shortname']}` |")
    if tour.get('arctic_id'):
        lines.append(f"| **Arctic ID** | {tour['arctic_id']} |")
    lines.append("")

    # Tour Info section (read-only)
    lines.append("---")
    lines.append("## 📋 Tour Information")
    lines.append("")

    info_items = [
        ("Tour Type", tour.get('tour_type')),
        ("Region", tour.get('region')),
        ("Duration", tour.get('duration')),
        ("Season", tour.get('season')),
        ("Style", tour.get('style')),
        ("Skill Level", tour.get('skill_level')),
        ("Departs From", tour.get('departs')),
        ("Distance", tour.get('distance')),
    ]

    for label, value in info_items:
        if value:
            lines.append(f"- **{label}:** {value}")

    if tour.get('permalink'):
        lines.append(f"- **Website:** [{tour['permalink']}]({tour['permalink']})")

    lines.append("")

    # Pricing section (read-only, from Arctic)
    if pricing or fees:
        lines.append("---")
        lines.append("## 💰 Pricing")
        lines.append("> Pricing is managed in Arctic Reservations.")
        lines.append("")

        if pricing:
            for ptype, variant, amount in pricing:
                label = f"{ptype.replace('_', ' ').title()}"
                if variant and variant != 'default':
                    label += f" ({variant})"
                lines.append(f"- **{label}:** {amount}")

        if fees:
            lines.append("")
            lines.append("**Additional Fees:**")
            for fee_type, amount in fees:
                lines.append(f"- {fee_type.replace('_', ' ').title()}: {amount}")

        lines.append("")

    # ========================================
    # EDITABLE FIELDS SECTION (with markers)
    # ========================================
    lines.append("---")
    lines.append("## ✏️ Editable Content")
    lines.append("> Edit content between the markers. Changes sync back to database.")
    lines.append("")

    # Short Description
    lines.append("### Short Description")
    lines.append("<!-- FIELD:short_description -->")
    lines.append(tour.get('short_description') or "_Enter a brief 1-2 sentence description._")
    lines.append("<!-- /FIELD:short_description -->")
    lines.append("")

    # Full Description
    lines.append("### Full Description")
    lines.append("<!-- FIELD:description -->")
    lines.append(tour.get('description') or "_Enter the full tour description._")
    lines.append("<!-- /FIELD:description -->")
    lines.append("")

    # Special Notes
    lines.append("### Special Notes")
    lines.append("<!-- FIELD:special_notes -->")
    lines.append(tour.get('special_notes') or "_Any special notes or requirements._")
    lines.append("<!-- /FIELD:special_notes -->")
    lines.append("")

    # Meeting Information
    lines.append("### Meeting Information")
    lines.append("<!-- FIELD:meeting_time -->")
    lines.append(f"**Time:** {tour.get('meeting_time') or '_e.g., 8:30 AM_'}")
    lines.append("<!-- /FIELD:meeting_time -->")
    lines.append("")
    lines.append("<!-- FIELD:meeting_location -->")
    lines.append(f"**Location:** {tour.get('meeting_location') or '_e.g., Rim Tours HQ, 1233 S Hwy 191_'}")
    lines.append("<!-- /FIELD:meeting_location -->")
    lines.append("")

    # Difficulty & Terrain
    lines.append("### Difficulty & Terrain")
    lines.append("<!-- FIELD:tour_rating -->")
    lines.append(f"**Tour Rating:** {tour.get('tour_rating') or '_e.g., Moderate/Intermediate_'}")
    lines.append("<!-- /FIELD:tour_rating -->")
    lines.append("")
    lines.append("<!-- FIELD:terrain -->")
    lines.append(f"**Terrain:** {tour.get('terrain') or '_Describe the terrain._'}")
    lines.append("<!-- /FIELD:terrain -->")
    lines.append("")
    lines.append("<!-- FIELD:technical_difficulty -->")
    lines.append(f"**Technical Difficulty:** {tour.get('technical_difficulty') or '_Describe technical aspects._'}")
    lines.append("<!-- /FIELD:technical_difficulty -->")
    lines.append("")
    lines.append("<!-- FIELD:altitude -->")
    lines.append(f"**Altitude:** {tour.get('altitude') or '_e.g., 4,500ft to 6,000ft_'}")
    lines.append("<!-- /FIELD:altitude -->")
    lines.append("")

    # Itinerary Days (if available)
    if itinerary_days:
        lines.append("### Day-by-Day Itinerary")
        lines.append("")
        for day in itinerary_days:
            day_num = day['day_number']
            lines.append(f"#### Day {day_num}")
            lines.append(f"<!-- ITINERARY_DAY:{day_num} -->")
            lines.append("")
            lines.append(f"**Miles:** {day.get('miles') or '_TBD_'}")
            lines.append(f"**Elevation:** {day.get('elevation') or '_TBD_'}")
            lines.append(f"**Route:** {day.get('trails_waypoints') or '_TBD_'}")
            lines.append(f"**Lodging:** {day.get('camp_lodging') or '_TBD_'}")
            lines.append(f"**Meals:** {day.get('meals') or '_TBD_'}")
            lines.append("")
            lines.append(day.get('content') or "_Day description._")
            lines.append("")
            lines.append(f"<!-- /ITINERARY_DAY:{day_num} -->")
            lines.append("")

    # Separator before legacy content
    lines.append("---")
    lines.append("## 📜 Legacy Content")
    lines.append("> Previous content preserved below. Move relevant info to editable fields above.")
    lines.append("")

    return "\n".join(lines)


def generate_tour_document(tour, itinerary_days, pricing, fees):
    """Generate Markdown document content for a tour."""
    lines = []

    # Header with tour title
    lines.append(f"# {tour['title']}")
    lines.append("")

    if tour.get('subtitle'):
        lines.append(f"*{tour['subtitle']}*")
        lines.append("")

    # ========================================
    # READ-ONLY: Reference Identifiers
    # ========================================
    lines.append("---")
    lines.append("## 🔗 Reference IDs")
    lines.append("> ⚠️ **Read-Only** - Cross-system identifiers for this tour.")
    lines.append("")
    lines.append("| System | Identifier |")
    lines.append("|--------|------------|")
    lines.append(f"| **Title** | {tour['title']} |")
    if tour.get('slug'):
        lines.append(f"| **Slug** | `{tour['slug']}` |")
    if tour.get('website_id'):
        lines.append(f"| **Website ID** | {tour['website_id']} |")
    if tour.get('arctic_shortname'):
        lines.append(f"| **Arctic Shortname** | `{tour['arctic_shortname']}` |")
    if tour.get('arctic_id'):
        lines.append(f"| **Arctic ID** | {tour['arctic_id']} |")
    lines.append("")

    # ========================================
    # READ-ONLY: Classification Info
    # ========================================
    lines.append("---")
    lines.append("## 📋 Tour Information")
    lines.append("> ⚠️ **Read-Only Section** - This data comes from the website and cannot be edited here.")
    lines.append("")

    info_items = [
        ("Tour Type", tour.get('tour_type')),
        ("Region", tour.get('region')),
        ("Duration", tour.get('duration')),
        ("Season", tour.get('season')),
        ("Style", tour.get('style')),
        ("Skill Level", tour.get('skill_level')),
        ("Departs From", tour.get('departs')),
        ("Distance", tour.get('distance')),
    ]

    for label, value in info_items:
        if value:
            lines.append(f"- **{label}:** {value}")

    if tour.get('permalink'):
        lines.append(f"- **Website:** [{tour['permalink']}]({tour['permalink']})")

    lines.append("")

    # ========================================
    # READ-ONLY: Pricing (from Arctic)
    # ========================================
    if pricing or fees:
        lines.append("---")
        lines.append("## 💰 Pricing")
        lines.append("> ⚠️ **Read-Only Section** - Pricing is managed in Arctic Reservations.")
        lines.append("")

        if pricing:
            for ptype, variant, amount in pricing:
                label = f"{ptype.replace('_', ' ').title()}"
                if variant and variant != 'default':
                    label += f" ({variant})"
                lines.append(f"- **{label}:** {amount}")

        if fees:
            lines.append("")
            lines.append("**Additional Fees:**")
            for fee_type, amount in fees:
                lines.append(f"- {fee_type.replace('_', ' ').title()}: {amount}")

        lines.append("")

    # ========================================
    # EDITABLE: Description
    # ========================================
    lines.append("---")
    lines.append("## ✏️ Description")
    lines.append("> ✅ **Editable Section** - You can edit this content.")
    lines.append("")

    lines.append("### Short Description")
    lines.append("<!-- FIELD:short_description -->")
    lines.append(tour.get('short_description') or "_No short description yet._")
    lines.append("<!-- /FIELD:short_description -->")
    lines.append("")

    lines.append("### Full Description")
    lines.append("<!-- FIELD:description -->")
    lines.append(tour.get('description') or "_No description yet._")
    lines.append("<!-- /FIELD:description -->")
    lines.append("")

    if tour.get('special_notes'):
        lines.append("### Special Notes")
        lines.append("<!-- FIELD:special_notes -->")
        lines.append(tour['special_notes'])
        lines.append("<!-- /FIELD:special_notes -->")
        lines.append("")

    # ========================================
    # EDITABLE: Trip Details
    # ========================================
    lines.append("---")
    lines.append("## ✏️ Trip Details")
    lines.append("> ✅ **Editable Section** - You can edit this content.")
    lines.append("")

    lines.append("### Meeting Information")
    lines.append("<!-- FIELD:meeting_time -->")
    lines.append(f"**Time:** {tour.get('meeting_time') or '_Not specified_'}")
    lines.append("<!-- /FIELD:meeting_time -->")
    lines.append("")
    lines.append("<!-- FIELD:meeting_location -->")
    lines.append(f"**Location:** {tour.get('meeting_location') or '_Not specified_'}")
    lines.append("<!-- /FIELD:meeting_location -->")
    lines.append("")

    lines.append("### Difficulty & Terrain")
    lines.append("<!-- FIELD:tour_rating -->")
    lines.append(f"**Tour Rating:** {tour.get('tour_rating') or '_Not specified_'}")
    lines.append("<!-- /FIELD:tour_rating -->")
    lines.append("")
    lines.append("<!-- FIELD:terrain -->")
    lines.append(f"**Terrain:** {tour.get('terrain') or '_Not specified_'}")
    lines.append("<!-- /FIELD:terrain -->")
    lines.append("")
    lines.append("<!-- FIELD:technical_difficulty -->")
    lines.append(f"**Technical Difficulty:** {tour.get('technical_difficulty') or '_Not specified_'}")
    lines.append("<!-- /FIELD:technical_difficulty -->")
    lines.append("")
    lines.append("<!-- FIELD:altitude -->")
    lines.append(f"**Altitude:** {tour.get('altitude') or '_Not specified_'}")
    lines.append("<!-- /FIELD:altitude -->")
    lines.append("")

    # ========================================
    # EDITABLE: Itinerary
    # ========================================
    if itinerary_days:
        lines.append("---")
        lines.append("## ✏️ Day-by-Day Itinerary")
        lines.append("> ✅ **Editable Section** - You can edit this content.")
        lines.append("")

        for day in itinerary_days:
            day_num = day['day_number']
            lines.append(f"### Day {day_num}")
            lines.append(f"<!-- ITINERARY_DAY:{day_num} -->")
            lines.append("")

            stats = []
            if day.get('miles'):
                stats.append(f"**Miles:** {day['miles']}")
            if day.get('elevation'):
                stats.append(f"**Elevation:** {day['elevation']}")
            if stats:
                lines.append(" | ".join(stats))
                lines.append("")

            if day.get('trails_waypoints'):
                lines.append(f"**Route:** {day['trails_waypoints']}")
                lines.append("")

            if day.get('camp_lodging'):
                lines.append(f"**Lodging:** {day['camp_lodging']}")
                lines.append("")

            if day.get('meals'):
                lines.append(f"**Meals:** {day['meals']}")
                lines.append("")

            if day.get('content'):
                lines.append(day['content'])
                lines.append("")

            lines.append(f"<!-- /ITINERARY_DAY:{day_num} -->")
            lines.append("")

    # ========================================
    # Footer with sync info
    # ========================================
    lines.append("---")
    lines.append("*This document is synced with the RimTours database.*")
    lines.append(f"*Last sync: {datetime.now().strftime('%Y-%m-%d %H:%M')}*")

    return "\n".join(lines)


def parse_outline_document(text):
    """Parse an Outline document and extract editable field values."""
    parsed = {
        'fields': {},
        'itinerary_days': [],
    }

    # Extract field values using markers
    field_pattern = r'<!-- FIELD:(\w+) -->\s*(.*?)\s*<!-- /FIELD:\1 -->'
    for match in re.finditer(field_pattern, text, re.DOTALL):
        field_name = match.group(1)
        field_value = match.group(2).strip()

        # Clean up the value (remove markdown formatting for simple fields)
        if field_name in ['meeting_time', 'meeting_location', 'tour_rating',
                          'terrain', 'technical_difficulty', 'altitude']:
            # Extract value after "**Label:**"
            value_match = re.search(r'\*\*[^*]+:\*\*\s*(.+)', field_value)
            if value_match:
                field_value = value_match.group(1).strip()
                if field_value == '_Not specified_':
                    field_value = ''

        if field_value and field_value != '_No short description yet._' and \
           field_value != '_No description yet._':
            parsed['fields'][field_name] = field_value

    # Extract itinerary days
    day_pattern = r'<!-- ITINERARY_DAY:(\d+) -->\s*(.*?)\s*<!-- /ITINERARY_DAY:\1 -->'
    for match in re.finditer(day_pattern, text, re.DOTALL):
        day_num = int(match.group(1))
        day_content = match.group(2).strip()

        day_data = {'day_number': day_num}

        # Parse miles
        miles_match = re.search(r'\*\*Miles:\*\*\s*([^\n|]+)', day_content)
        if miles_match:
            day_data['miles'] = miles_match.group(1).strip()

        # Parse elevation
        elev_match = re.search(r'\*\*Elevation:\*\*\s*([^\n|]+)', day_content)
        if elev_match:
            day_data['elevation'] = elev_match.group(1).strip()

        # Parse route
        route_match = re.search(r'\*\*Route:\*\*\s*([^\n]+)', day_content)
        if route_match:
            day_data['trails_waypoints'] = route_match.group(1).strip()

        # Parse lodging
        lodging_match = re.search(r'\*\*Lodging:\*\*\s*([^\n]+)', day_content)
        if lodging_match:
            day_data['camp_lodging'] = lodging_match.group(1).strip()

        # Parse meals
        meals_match = re.search(r'\*\*Meals:\*\*\s*([^\n]+)', day_content)
        if meals_match:
            day_data['meals'] = meals_match.group(1).strip()

        # Remaining content (after removing parsed parts)
        remaining = day_content
        for pattern in [r'\*\*Miles:\*\*[^\n|]+', r'\*\*Elevation:\*\*[^\n|]+',
                       r'\*\*Route:\*\*[^\n]+', r'\*\*Lodging:\*\*[^\n]+',
                       r'\*\*Meals:\*\*[^\n]+', r'\|']:
            remaining = re.sub(pattern, '', remaining)
        remaining = remaining.strip()
        if remaining:
            day_data['content'] = remaining

        parsed['itinerary_days'].append(day_data)

    return parsed


# ==========================================
# SYNC OPERATIONS
# ==========================================

def strip_existing_header(text):
    """Remove previously added header sections, keeping only legacy content."""
    # Find where legacy content starts
    legacy_marker = "## 📜 Legacy Content"
    if legacy_marker in text:
        # Keep everything after the legacy marker line
        idx = text.find(legacy_marker)
        # Find the end of that line and the instruction line
        lines = text[idx:].split('\n')
        # Skip the header line and instruction line
        content_start = 0
        for i, line in enumerate(lines):
            if i > 1 and line.strip() and not line.startswith('>'):
                content_start = i
                break
        return '\n'.join(lines[content_start:]).strip()

    # If no legacy marker, check for old "Tour Details" marker
    old_marker = "## 📝 Tour Details"
    if old_marker in text:
        idx = text.find(old_marker)
        lines = text[idx:].split('\n')
        content_start = 0
        for i, line in enumerate(lines):
            if i > 1 and line.strip() and not line.startswith('>') and not line.startswith('*'):
                content_start = i
                break
        return '\n'.join(lines[content_start:]).strip()

    # If header exists but no markers, try to find content after pricing
    if '## 🔗 Reference IDs' in text:
        # This is our header, but missing legacy marker - return empty
        return ""

    # No header found, return original
    return text


def push_tour_to_outline(conn, tour, existing_docs, dry_run=False, force_update=False):
    """Push a single tour to Outline - prepends reference header to existing docs."""
    tour_id = tour['id']
    slug = tour.get('slug', '')

    # Get related data
    itinerary_days = get_tour_itinerary(conn, tour_id)
    pricing = get_tour_pricing(conn, tour_id)
    fees = get_tour_fees(conn, tour_id)

    # Check if doc exists by slug
    existing = existing_docs.get(slug)

    if dry_run:
        return {
            'tour_id': tour_id,
            'title': tour['title'],
            'slug': slug,
            'action': 'update' if (existing and force_update) else ('prepend' if existing else 'create'),
            'existing_doc_id': existing['id'] if existing else None,
        }

    try:
        if existing:
            # Fetch existing document content
            existing_doc = get_outline_document(existing['id'])
            existing_text = existing_doc.get('text', '') if existing_doc else ''

            # Check if we should skip (already has markers) unless force_update
            if '## ✏️ Editable Content' in existing_text and not force_update:
                return {
                    'tour_id': tour_id,
                    'title': tour['title'],
                    'slug': slug,
                    'action': 'skipped',
                    'reason': 'markers_exist'
                }

            # Strip any existing header to get just the legacy content
            legacy_content = strip_existing_header(existing_text)

            # Generate new header with editable markers
            header = generate_reference_header(tour, pricing, fees, itinerary_days)

            # Combine header + legacy content
            if legacy_content:
                new_text = header + "\n" + legacy_content
            else:
                new_text = header

            # Update document
            doc = update_outline_document(existing['id'], text=new_text)
            update_tour_outline_doc_id(conn, tour_id, existing['id'])
            action = 'updated' if force_update else 'prepended'

        else:
            # Create new document with full content
            doc_text = generate_tour_document(tour, itinerary_days, pricing, fees)

            # Determine parent based on tour type
            parent_doc_id = OUTLINE_DAY_TOURS_DOC_ID if is_day_tour(tour) else OUTLINE_MD_TOURS_DOC_ID

            doc = create_outline_document(
                title=slug or tour['title'],  # Use slug as doc title
                text=doc_text,
                collection_id=OUTLINE_COLLECTION_ID,
                parent_doc_id=parent_doc_id
            )
            update_tour_outline_doc_id(conn, tour_id, doc['id'])
            action = 'created'

        log_sync(conn, 'outline_push', tour_id, 'success', {'action': action})
        return {'tour_id': tour_id, 'title': tour['title'], 'slug': slug, 'action': action, 'doc_id': doc['id']}

    except Exception as e:
        log_sync(conn, 'outline_push', tour_id, 'failed', error=str(e))
        return {'tour_id': tour_id, 'title': tour['title'], 'slug': slug, 'action': 'error', 'error': str(e)}


def pull_tour_from_outline(conn, tour, dry_run=False):
    """Pull changes from Outline document back to PostgreSQL."""
    tour_id = tour['id']
    doc_id = tour.get('outline_doc_id')

    if not doc_id:
        return {'tour_id': tour_id, 'title': tour['title'], 'action': 'skipped', 'reason': 'no_doc_id'}

    try:
        # Fetch document from Outline
        doc = get_outline_document(doc_id)
        if not doc:
            return {'tour_id': tour_id, 'title': tour['title'], 'action': 'error', 'error': 'Document not found'}

        # Parse document content
        parsed = parse_outline_document(doc.get('text', ''))

        if dry_run:
            return {
                'tour_id': tour_id,
                'title': tour['title'],
                'action': 'would_update',
                'fields': list(parsed['fields'].keys()),
                'itinerary_days': len(parsed['itinerary_days']),
            }

        # Update tour fields
        fields_updated = update_tour_from_outline(conn, tour_id, parsed['fields'])

        # Update itinerary days
        days_updated = 0
        if parsed['itinerary_days']:
            days_updated = update_itinerary_from_outline(conn, tour_id, parsed['itinerary_days'])

        log_sync(conn, 'outline_pull', tour_id, 'success', {
            'fields_updated': fields_updated,
            'days_updated': days_updated,
        })

        return {
            'tour_id': tour_id,
            'title': tour['title'],
            'action': 'updated',
            'fields_updated': fields_updated,
            'days_updated': days_updated,
        }

    except Exception as e:
        log_sync(conn, 'outline_pull', tour_id, 'failed', error=str(e))
        return {'tour_id': tour_id, 'title': tour['title'], 'action': 'error', 'error': str(e)}


def push_all_to_outline(dry_run=False, force_update=False):
    """Push all tours to Outline - prepends reference headers with editable markers."""
    print("=" * 60)
    title = "PUSH TO OUTLINE"
    if force_update:
        title += " (FORCE UPDATE)"
    if dry_run:
        title += " (DRY RUN)"
    print(title)
    print("=" * 60)

    if not OUTLINE_API_KEY:
        print("\nERROR: OUTLINE_API_KEY not set in .env")
        print("Set the following environment variables:")
        print("  OUTLINE_API_URL=https://your-outline.com/api")
        print("  OUTLINE_API_KEY=your_api_key")
        print("  OUTLINE_COLLECTION_ID=collection_id_for_tours")
        return

    # Get existing Outline docs by slug
    print("\nFetching existing Outline documents...")
    existing_docs = get_existing_tour_docs()
    print(f"  Found {len(existing_docs)} existing tour documents")

    conn = get_db_connection()
    tours = get_tours_from_db(conn)

    print(f"\nProcessing {len(tours)} tours from database...")

    results = {'created': 0, 'updated': 0, 'prepended': 0, 'skipped': 0, 'errors': 0, 'no_slug': 0}

    for tour in tours:
        slug = tour.get('slug', '')
        if not slug:
            results['no_slug'] += 1
            print(f"  ? {tour['title']} - no slug, skipping")
            continue

        result = push_tour_to_outline(conn, tour, existing_docs, dry_run, force_update)

        if result['action'] == 'create' or result['action'] == 'created':
            results['created'] += 1
            print(f"  + {slug}")
        elif result['action'] == 'update' or result['action'] == 'updated':
            results['updated'] += 1
            print(f"  ~ {slug}")
        elif result['action'] == 'prepend' or result['action'] == 'prepended':
            results['prepended'] += 1
            print(f"  ^ {slug}")
        elif result['action'] == 'skipped':
            results['skipped'] += 1
            print(f"  - {slug} (markers exist)")
        elif result['action'] == 'error':
            results['errors'] += 1
            print(f"  ! {slug}: {result.get('error', 'Unknown error')}")

    conn.close()

    print(f"\nResults:")
    print(f"  Updated (force): {results['updated']}")
    print(f"  Prepended markers: {results['prepended']}")
    print(f"  Created new: {results['created']}")
    print(f"  Skipped (markers exist): {results['skipped']}")
    print(f"  No slug: {results['no_slug']}")
    print(f"  Errors: {results['errors']}")


def pull_all_from_outline(dry_run=False):
    """Pull changes from all Outline documents back to PostgreSQL."""
    print("=" * 60)
    print("PULL FROM OUTLINE" + (" (DRY RUN)" if dry_run else ""))
    print("=" * 60)

    if not OUTLINE_API_KEY:
        print("\nERROR: OUTLINE_API_KEY not set in .env")
        return

    conn = get_db_connection()
    tours = get_tours_from_db(conn)

    # Filter to tours with Outline doc IDs
    linked_tours = [t for t in tours if t.get('outline_doc_id')]

    print(f"\nProcessing {len(linked_tours)} linked tours (out of {len(tours)} total)...")

    results = {'updated': 0, 'skipped': 0, 'errors': 0}

    for tour in linked_tours:
        result = pull_tour_from_outline(conn, tour, dry_run)

        if result['action'] == 'updated' or result['action'] == 'would_update':
            results['updated'] += 1
            print(f"  ~ {tour['title']}")
        elif result['action'] == 'skipped':
            results['skipped'] += 1
        elif result['action'] == 'error':
            results['errors'] += 1
            print(f"  ! {tour['title']}: {result.get('error', 'Unknown error')}")

    conn.close()

    print(f"\nResults:")
    print(f"  Updated: {results['updated']}")
    print(f"  Skipped: {results['skipped']}")
    print(f"  Errors: {results['errors']}")


def generate_local_preview(output_dir='outline_preview'):
    """Generate local Markdown files for preview (no Outline API needed)."""
    print("=" * 60)
    print("GENERATING LOCAL PREVIEW")
    print("=" * 60)

    import os
    os.makedirs(output_dir, exist_ok=True)

    conn = get_db_connection()
    tours = get_tours_from_db(conn)

    print(f"\nGenerating {len(tours)} tour documents...")

    for tour in tours:
        tour_id = tour['id']

        # Get related data
        itinerary_days = get_tour_itinerary(conn, tour_id)
        pricing = get_tour_pricing(conn, tour_id)
        fees = get_tour_fees(conn, tour_id)

        # Generate document content
        doc_text = generate_tour_document(tour, itinerary_days, pricing, fees)

        # Create safe filename
        safe_name = re.sub(r'[^\w\s-]', '', tour['title']).strip()
        safe_name = re.sub(r'[-\s]+', '-', safe_name)
        filename = f"{output_dir}/{safe_name}.md"

        with open(filename, 'w', encoding='utf-8') as f:
            f.write(doc_text)

        print(f"  + {tour['title']}")

    conn.close()

    print(f"\nPreview files saved to: {output_dir}/")


# ==========================================
# CLI
# ==========================================

def main():
    import sys

    if len(sys.argv) < 2:
        print("Usage: python outline_sync.py <command> [options]")
        print("")
        print("Commands:")
        print("  push [--dry-run] [--force]  Push all tours to Outline")
        print("  pull [--dry-run]            Pull changes from Outline to PostgreSQL")
        print("  preview                     Generate local Markdown preview (no API needed)")
        print("")
        print("Options:")
        print("  --dry-run    Show what would happen without making changes")
        print("  --force      Update docs even if markers already exist")
        print("")
        print("Environment variables needed for push/pull:")
        print("  OUTLINE_API_URL     Outline API URL")
        print("  OUTLINE_API_KEY     Outline API key")
        print("  OUTLINE_COLLECTION_ID  Collection ID for tour documents")
        return

    command = sys.argv[1]
    dry_run = '--dry-run' in sys.argv
    force_update = '--force' in sys.argv

    if command == 'push':
        push_all_to_outline(dry_run, force_update)
    elif command == 'pull':
        pull_all_from_outline(dry_run)
    elif command == 'preview':
        generate_local_preview()
    else:
        print(f"Unknown command: {command}")


if __name__ == "__main__":
    main()
