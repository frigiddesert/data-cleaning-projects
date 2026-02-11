#!/usr/bin/env python3
"""
Sync Arctic Reservations availability data to Outline tour documents.

Updates the <!-- ARCTIC_SYNC:schedule --> sections in tour documents with
current availability data from Arctic.

Usage:
    python sync_arctic_availability.py           # Sync all tours
    python sync_arctic_availability.py --tour WR4  # Sync specific tour
    python sync_arctic_availability.py --dry-run   # Preview changes
"""

import os
import re
import argparse
from datetime import datetime
from typing import Dict, List, Optional
import requests
from dotenv import load_dotenv

from arctic_client import ArcticClient

# Load environment - use explicit path for reliability
load_dotenv('/home/eric/code/data-cleaning-projects/.env')

# Outline API Configuration
OUTLINE_API_URL = os.getenv('OUTLINE_API_URL')
OUTLINE_API_KEY = os.getenv('OUTLINE_API_KEY')
OUTLINE_HEADERS = {
    'Authorization': f'Bearer {OUTLINE_API_KEY}',
    'Content-Type': 'application/json'
}

# Collection and folder IDs
RIM_SSOT_COLLECTION = 'e6a61047-77ad-4e96-a10b-2007962c07fb'
OUTLINE_DAY_TOURS = os.environ.get('OUTLINE_DAY_TOURS_DOC_ID', '')
OUTLINE_MD_TOURS = os.environ.get('OUTLINE_MD_TOURS_DOC_ID', '')


def outline_request(endpoint: str, data: dict) -> dict:
    """Make a POST request to Outline API."""
    url = f"{OUTLINE_API_URL}/{endpoint}"
    response = requests.post(url, headers=OUTLINE_HEADERS, json=data)
    response.raise_for_status()
    return response.json()


def get_tour_documents() -> List[Dict]:
    """Get all tour documents from definitive folders (Day Tours + Multi-Day Tours)."""
    all_docs = []

    # Fetch from Day Tours folder
    if OUTLINE_DAY_TOURS:
        result = outline_request('documents.list', {
            'parentDocumentId': OUTLINE_DAY_TOURS,
            'limit': 100
        })
        all_docs.extend(result.get('data', []))

    # Fetch from Multi-Day Tours folder
    if OUTLINE_MD_TOURS:
        result = outline_request('documents.list', {
            'parentDocumentId': OUTLINE_MD_TOURS,
            'limit': 100
        })
        all_docs.extend(result.get('data', []))

    # All documents in these folders are tour documents
    # (They're already in the definitive Day Tours and Multi-Day Tours folders)
    return all_docs


def get_document_content(doc_id: str) -> str:
    """Get full document content from Outline."""
    result = outline_request('documents.info', {'id': doc_id})
    return result.get('data', {}).get('text', '')


def update_document(doc_id: str, content: str) -> bool:
    """Update document content in Outline."""
    try:
        outline_request('documents.update', {
            'id': doc_id,
            'text': content,
            'done': True
        })
        return True
    except Exception as e:
        print(f"  Error updating document: {e}")
        return False


def extract_arctic_id(content: str) -> Optional[int]:
    """Extract Arctic trip type ID from document Reference section."""
    # Look for Arctic ID in Reference table: | Arctic | tt191 |
    match = re.search(r'\|\s*Arctic\s*\|\s*tt(\d+)\s*\|', content)
    if match:
        return int(match.group(1))
    return None


def format_availability_table(schedule_data: Dict) -> str:
    """Format Arctic schedule data as markdown table with color-coded status."""
    future = schedule_data.get('future', [])

    if not future:
        return "No upcoming dates scheduled."

    lines = [
        "| Date | Spots | Status |",
        "|------|-------|--------|"
    ]

    for trip in future[:30]:  # Limit to next 30 dates
        date = trip['start_date']
        spots_available = trip['spots_available']
        spots_total = trip['spots_total']
        guests_booked = spots_total - spots_available

        # Color-coded status:
        # ⚪ Gray = No guests yet (empty, fully open)
        # 🟢 Green = Available (has bookings but spots open)
        # 🟡 Yellow = Limited (3 or fewer spots left)
        # 🔴 Red = Full (sold out)
        if spots_available == 0:
            status = "🔴 Full"
        elif spots_available <= 3:
            status = "🟡 Limited"
        elif guests_booked == 0:
            status = "⚪ Open"
        else:
            status = "🟢 Available"

        # Format date nicely
        try:
            dt = datetime.strptime(date, '%Y-%m-%d')
            date_str = dt.strftime('%b %d, %Y')
        except:
            date_str = date

        lines.append(f"| {date_str} | {spots_available}/{spots_total} | {status} |")

    if len(future) > 30:
        lines.append(f"| ... | +{len(future) - 30} more | |")

    return '\n'.join(lines)


def format_pricing_table(pricing_data: Dict) -> str:
    """Format Arctic pricing data as markdown table."""
    pricing = pricing_data.get('pricing', [])

    if not pricing:
        return "Contact for pricing."

    lines = [
        "| Option | Price |",
        "|--------|-------|"
    ]

    for level in pricing:
        if level.get('show_online', True):
            name = level['name']
            amount = level['amount']
            lines.append(f"| {name} | ${amount:,.0f} |")

    return '\n'.join(lines)


def update_arctic_sync_section(content: str, section_type: str, new_content: str) -> str:
    """Replace an ARCTIC_SYNC section with new content, or insert if missing."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    # Pattern to match the section
    pattern = rf'(<!-- ARCTIC_SYNC:{section_type} -->)(.*?)(<!-- /ARCTIC_SYNC -->)'

    if section_type == 'schedule':
        # Use America/Denver timezone for timestamp
        denver_tz = ZoneInfo('America/Denver')
        timestamp = datetime.now(denver_tz).strftime('%Y-%m-%d %H:%M:%S %Z')
        replacement = f'<!-- ARCTIC_SYNC:{section_type} -->\n\n*Last synced: {timestamp}*\n\n## Scheduled Dates\n\n{new_content}\n\n<!-- /ARCTIC_SYNC -->'
    elif section_type == 'pricing':
        replacement = f'<!-- ARCTIC_SYNC:{section_type} -->\n\n## Pricing\n\n{new_content}\n\n<!-- /ARCTIC_SYNC -->'
    else:
        replacement = f'<!-- ARCTIC_SYNC:{section_type} -->\n\n{new_content}\n\n<!-- /ARCTIC_SYNC -->'

    new_text, count = re.subn(pattern, replacement, content, flags=re.DOTALL)

    # If section didn't exist, insert it after Reference section (for schedule)
    if count == 0 and section_type == 'schedule':
        # Find end of Reference section
        ref_end = content.find('---', content.find('## Reference'))
        if ref_end > 0:
            # Insert after the --- following Reference
            insert_point = ref_end + 3
            new_text = content[:insert_point] + f'\n\n{replacement}\n' + content[insert_point:]
            return new_text

    return new_text if count > 0 else content


def sync_tour(doc: Dict, arctic_client: ArcticClient, dry_run: bool = False) -> bool:
    """Sync a single tour document with Arctic data."""
    doc_id = doc['id']
    title = doc['title']

    print(f"\n{title}")

    # Get full document content
    content = get_document_content(doc_id)

    # Extract Arctic ID
    arctic_id = extract_arctic_id(content)
    if not arctic_id:
        print(f"  ⚠ No Arctic ID found in document")
        return False

    print(f"  Arctic ID: tt{arctic_id}")

    # Get Arctic data
    try:
        schedule = arctic_client.get_full_schedule(arctic_id)
        pricing = arctic_client.get_trip_pricing_summary(arctic_id)
    except Exception as e:
        print(f"  ❌ Error fetching Arctic data: {e}")
        return False

    # Format new content
    schedule_table = format_availability_table(schedule)
    pricing_table = format_pricing_table(pricing)

    # Update content
    new_content = content

    # Update schedule section
    if '<!-- ARCTIC_SYNC:schedule -->' in content:
        new_content = update_arctic_sync_section(new_content, 'schedule', schedule_table)
        print(f"  📅 Schedule: {schedule.get('total_future', 0)} upcoming dates")

    # Update pricing section
    if '<!-- ARCTIC_SYNC:pricing -->' in content:
        new_content = update_arctic_sync_section(new_content, 'pricing', pricing_table)
        print(f"  💰 Pricing: {len(pricing.get('pricing', []))} levels")

    # Check if content changed
    if new_content == content:
        print(f"  ✓ No changes needed")
        return True

    if dry_run:
        print(f"  🔍 Would update (dry run)")
        return True

    # Update document
    if update_document(doc_id, new_content):
        print(f"  ✅ Updated")
        return True
    else:
        print(f"  ❌ Update failed")
        return False


def main():
    parser = argparse.ArgumentParser(description='Sync Arctic availability to Outline')
    parser.add_argument('--tour', help='Sync specific tour by code (e.g., WR4)')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without updating')
    args = parser.parse_args()

    print("=" * 60)
    print("ARCTIC → OUTLINE AVAILABILITY SYNC")
    print("=" * 60)

    if args.dry_run:
        print("DRY RUN MODE - No changes will be made")

    # Initialize Arctic client
    arctic = ArcticClient()

    # Get tour documents
    print("\nFetching tour documents from Outline...")
    tours = get_tour_documents()
    print(f"Found {len(tours)} tour documents")

    # Filter to specific tour if requested
    if args.tour:
        tours = [t for t in tours if t['title'].upper().startswith(args.tour.upper())]
        if not tours:
            print(f"No tour found matching '{args.tour}'")
            return

    # Sync each tour
    success = 0
    failed = 0
    skipped = 0

    for tour in tours:
        result = sync_tour(tour, arctic, dry_run=args.dry_run)
        if result:
            success += 1
        elif result is None:
            skipped += 1
        else:
            failed += 1

    # Summary
    print("\n" + "=" * 60)
    print(f"SYNC COMPLETE: {success} updated, {failed} failed, {skipped} skipped")
    print("=" * 60)


if __name__ == "__main__":
    main()
