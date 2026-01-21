#!/usr/bin/env python3
"""
Outline Tour Document Consolidation

Consolidates 84 Outline tour documents with:
- Arctic-synced pricing and schedules
- Clean naming: {arctic_shortname} - {full_name}
- A/B testing content variations
- Consistent template structure

Commands:
    python outline_consolidate.py backup              # Backup all docs
    python outline_consolidate.py rename --dry-run    # Preview title changes
    python outline_consolidate.py rename              # Apply new titles
    python outline_consolidate.py migrate --dry-run   # Preview content migration
    python outline_consolidate.py migrate             # Apply clean template
    python outline_consolidate.py sync pricing        # Update pricing from Arctic
    python outline_consolidate.py sync schedule       # Update schedules from Arctic
    python outline_consolidate.py rollback <backup>   # Restore from backup
"""

import argparse
import csv
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv

from arctic_client import ArcticClient, get_client as get_arctic_client

load_dotenv()

# ==========================================
# CONFIGURATION
# ==========================================

OUTLINE_API_URL = os.getenv('OUTLINE_API_URL', 'http://10.2.0.8:3200/api')
OUTLINE_API_KEY = os.getenv('OUTLINE_API_KEY', '')
OUTLINE_COLLECTION_ID = os.getenv('OUTLINE_COLLECTION_ID', '')

MASTER_LIST_PATH = Path(__file__).parent / 'tour_master_list.csv'
BACKUPS_DIR = Path(__file__).parent / 'backups'

# Rate limiting
API_DELAY_MS = 500


# ==========================================
# OUTLINE API FUNCTIONS
# ==========================================

def outline_request(endpoint: str, data: dict = None) -> dict:
    """Make a request to Outline API."""
    headers = {
        'Authorization': f'Bearer {OUTLINE_API_KEY}',
        'Content-Type': 'application/json',
    }
    url = f"{OUTLINE_API_URL}/{endpoint}"

    try:
        response = requests.post(url, headers=headers, json=data or {})
        if response.status_code != 200:
            raise Exception(f"HTTP {response.status_code}: {response.text[:200]}")
        return response.json()
    except Exception as e:
        raise Exception(f"Outline API error ({endpoint}): {e}")


def get_outline_document(doc_id: str) -> Optional[dict]:
    """Fetch a document from Outline by ID."""
    try:
        result = outline_request('documents.info', {'id': doc_id})
        return result.get('data')
    except:
        return None


def update_outline_document(doc_id: str, title: str = None, text: str = None) -> dict:
    """Update an existing document in Outline."""
    data = {'id': doc_id}
    if title is not None:
        data['title'] = title
    if text is not None:
        data['text'] = text

    result = outline_request('documents.update', data)
    return result.get('data')


def get_all_outline_documents() -> List[dict]:
    """Get all documents in the tours collection."""
    all_docs = []
    offset = 0
    limit = 100

    while True:
        result = outline_request('documents.list', {
            'collectionId': OUTLINE_COLLECTION_ID,
            'limit': limit,
            'offset': offset,
        })
        docs = result.get('data', [])
        if not docs:
            break
        all_docs.extend(docs)
        offset += len(docs)
        if len(docs) < limit:
            break

    return all_docs


# ==========================================
# MASTER LIST HANDLING
# ==========================================

def load_master_list() -> List[dict]:
    """Load tour_master_list.csv."""
    if not MASTER_LIST_PATH.exists():
        raise FileNotFoundError(f"Master list not found: {MASTER_LIST_PATH}")

    tours = []
    with open(MASTER_LIST_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Skip suppressed entries
            suppress = row.get('suppress', '').strip()
            if suppress == 'x':
                continue
            tours.append(row)

    return tours


def get_master_list_by_outline_uuid() -> Dict[str, dict]:
    """Get master list indexed by outline_uuid."""
    tours = load_master_list()
    return {t['outline_uuid']: t for t in tours if t.get('outline_uuid')}


def get_master_list_by_arctic_id() -> Dict[int, List[dict]]:
    """Get master list indexed by arctic_id (can have multiple docs per Arctic tour)."""
    tours = load_master_list()
    by_arctic = {}
    for t in tours:
        arctic_id = t.get('arctic_id')
        if arctic_id and arctic_id.isdigit():
            aid = int(arctic_id)
            if aid not in by_arctic:
                by_arctic[aid] = []
            by_arctic[aid].append(t)
    return by_arctic


# ==========================================
# BACKUP FUNCTIONS
# ==========================================

def create_backup_dir() -> Path:
    """Create timestamped backup directory."""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_dir = BACKUPS_DIR / f'outline_{timestamp}'
    backup_dir.mkdir(parents=True, exist_ok=True)
    return backup_dir


def backup_all_documents(verbose: bool = True) -> Path:
    """Backup all Outline tour documents."""
    if verbose:
        print("=" * 60)
        print("BACKUP ALL OUTLINE DOCUMENTS")
        print("=" * 60)

    backup_dir = create_backup_dir()
    manifest = []

    if verbose:
        print(f"\nBackup directory: {backup_dir}")
        print("\nFetching document list...")

    docs = get_all_outline_documents()
    if verbose:
        print(f"Found {len(docs)} documents\n")

    for i, doc in enumerate(docs, 1):
        doc_id = doc.get('id')
        title = doc.get('title', 'untitled')

        # Fetch full document content
        full_doc = get_outline_document(doc_id)
        if not full_doc:
            if verbose:
                print(f"  [{i}/{len(docs)}] ! {title} - fetch failed")
            continue

        # Save document
        safe_title = re.sub(r'[^\w\s-]', '', title)[:50]
        filename = f"{doc_id}_{safe_title}.json"
        filepath = backup_dir / filename

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(full_doc, f, indent=2, ensure_ascii=False)

        manifest.append({
            'id': doc_id,
            'title': title,
            'filename': filename,
            'url': full_doc.get('url', ''),
        })

        if verbose:
            print(f"  [{i}/{len(docs)}] + {title}")

        # Rate limit
        time.sleep(API_DELAY_MS / 1000)

    # Save manifest
    manifest_path = backup_dir / 'manifest.json'
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump({
            'created': datetime.now().isoformat(),
            'count': len(manifest),
            'documents': manifest,
        }, f, indent=2)

    if verbose:
        print(f"\nBackup complete: {len(manifest)} documents")
        print(f"Location: {backup_dir}")

    return backup_dir


def restore_from_backup(backup_path: str, dry_run: bool = False):
    """Restore documents from backup."""
    backup_dir = Path(backup_path)
    if not backup_dir.exists():
        # Try relative to backups dir
        backup_dir = BACKUPS_DIR / backup_path
        if not backup_dir.exists():
            raise FileNotFoundError(f"Backup not found: {backup_path}")

    manifest_path = backup_dir / 'manifest.json'
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found in backup: {manifest_path}")

    with open(manifest_path, 'r') as f:
        manifest = json.load(f)

    print("=" * 60)
    print(f"RESTORE FROM BACKUP {'(DRY RUN)' if dry_run else ''}")
    print("=" * 60)
    print(f"\nBackup: {backup_dir}")
    print(f"Created: {manifest.get('created', 'unknown')}")
    print(f"Documents: {manifest.get('count', 0)}\n")

    restored = 0
    errors = 0

    for doc_info in manifest.get('documents', []):
        doc_id = doc_info['id']
        title = doc_info['title']
        filename = doc_info['filename']

        filepath = backup_dir / filename
        if not filepath.exists():
            print(f"  ! {title} - backup file missing")
            errors += 1
            continue

        with open(filepath, 'r', encoding='utf-8') as f:
            backup_doc = json.load(f)

        if dry_run:
            print(f"  ~ {title} (would restore)")
        else:
            try:
                update_outline_document(
                    doc_id,
                    title=backup_doc.get('title'),
                    text=backup_doc.get('text'),
                )
                print(f"  + {title}")
                restored += 1
                time.sleep(API_DELAY_MS / 1000)
            except Exception as e:
                print(f"  ! {title} - {e}")
                errors += 1

    print(f"\nRestored: {restored}, Errors: {errors}")


# ==========================================
# RENAME FUNCTIONS
# ==========================================

def generate_new_title(arctic_shortname: str, arctic_name: str) -> str:
    """Generate new document title: {shortname} - {name}"""
    return f"{arctic_shortname} - {arctic_name}"


def rename_documents(dry_run: bool = False, limit: int = None):
    """Rename all documents using Arctic shortnames."""
    print("=" * 60)
    print(f"RENAME DOCUMENTS {'(DRY RUN)' if dry_run else ''}")
    print("=" * 60)

    # Load data
    arctic = get_arctic_client()
    shortname_map = arctic.get_shortname_map()
    name_map = arctic.get_name_map()
    master_by_uuid = get_master_list_by_outline_uuid()

    print(f"\nArctic: {len(shortname_map)} trip types")
    print(f"Master list: {len(master_by_uuid)} tour mappings")

    # Get Outline docs
    docs = get_all_outline_documents()
    print(f"Outline: {len(docs)} documents\n")

    renamed = 0
    skipped = 0
    errors = 0
    no_arctic = 0

    for doc in docs:
        if limit and renamed >= limit:
            print(f"\n  (limit of {limit} reached)")
            break

        doc_id = doc.get('id')
        current_title = doc.get('title', '')

        # Look up in master list
        master = master_by_uuid.get(doc_id)
        if not master:
            skipped += 1
            continue

        arctic_id = master.get('arctic_id')
        if not arctic_id or not arctic_id.isdigit():
            no_arctic += 1
            print(f"  ? {current_title} - no Arctic ID")
            continue

        arctic_id = int(arctic_id)
        shortname = shortname_map.get(arctic_id)
        name = name_map.get(arctic_id)

        if not shortname or not name:
            no_arctic += 1
            print(f"  ? {current_title} - Arctic ID {arctic_id} not found")
            continue

        new_title = generate_new_title(shortname, name)

        # Check if already correct
        if current_title == new_title:
            skipped += 1
            continue

        if dry_run:
            print(f"  ~ {current_title}")
            print(f"    -> {new_title}")
            renamed += 1
        else:
            try:
                update_outline_document(doc_id, title=new_title)
                print(f"  + {current_title} -> {new_title}")
                renamed += 1
                time.sleep(API_DELAY_MS / 1000)
            except Exception as e:
                print(f"  ! {current_title} - {e}")
                errors += 1

    print(f"\nResults:")
    print(f"  Renamed: {renamed}")
    print(f"  Skipped (already correct or not in master): {skipped}")
    print(f"  No Arctic ID: {no_arctic}")
    print(f"  Errors: {errors}")


# ==========================================
# DOCUMENT TEMPLATE
# ==========================================

DOCUMENT_TEMPLATE = """# {title}

> {short_description}

---

## Reference
| System | ID |
|--------|-----|
| Arctic | tt{arctic_id} |
| Website | {wp_permalink} |
| Outline | {outline_uuid} |

---

<!-- ARCTIC_SYNC:details -->
## Tour Details
| | |
|---|---|
| **Duration** | {duration} |
| **Group Size** | {group_size} |
| **Book By** | {cutoff} |
<!-- /ARCTIC_SYNC -->

---

<!-- ARCTIC_SYNC:pricing -->
## Pricing
{pricing_section}
<!-- /ARCTIC_SYNC -->

---

{schedule_section}

## Description
<!-- CONTENT:description -->
{description}
<!-- /CONTENT -->

---

{itinerary_section}

## A/B Testing
<!-- AB_TEST:headline -->
_No active A/B tests._
<!-- /AB_TEST -->

---

*Last sync: {timestamp}*
"""


def extract_description_from_doc(text: str) -> str:
    """Extract existing description content from document."""
    # Try to find CONTENT:description marker
    match = re.search(
        r'<!-- CONTENT:description -->\s*(.*?)\s*<!-- /CONTENT -->',
        text, re.DOTALL
    )
    if match:
        return match.group(1).strip()

    # Try to find FIELD:description marker (old format)
    match = re.search(
        r'<!-- FIELD:description -->\s*(.*?)\s*<!-- /FIELD:description -->',
        text, re.DOTALL
    )
    if match:
        return match.group(1).strip()

    # Try to find Description section
    match = re.search(
        r'##\s*(?:Full\s*)?Description\s*\n+(.*?)(?=\n##|\n---|\Z)',
        text, re.DOTALL | re.IGNORECASE
    )
    if match:
        content = match.group(1).strip()
        # Remove field markers if present
        content = re.sub(r'<!--[^>]+-->', '', content).strip()
        return content

    return "_Enter tour description._"


def extract_itinerary_from_doc(text: str) -> str:
    """Extract existing itinerary content from document."""
    # Try to find CONTENT:itinerary marker
    match = re.search(
        r'<!-- CONTENT:itinerary -->\s*(.*?)\s*<!-- /CONTENT -->',
        text, re.DOTALL
    )
    if match:
        return match.group(1).strip()

    # Try to find Itinerary section
    match = re.search(
        r'##\s*(?:Day-by-Day\s*)?Itinerary\s*\n+(.*?)(?=\n##|\n---|\Z)',
        text, re.DOTALL | re.IGNORECASE
    )
    if match:
        content = match.group(1).strip()
        # Clean up markers
        content = re.sub(r'<!--[^>]+-->', '', content).strip()
        return content

    return ""


def format_pricing_table(pricing: dict, is_multiday: bool) -> str:
    """Format pricing as markdown table."""
    lines = []

    if not pricing.get('pricing'):
        return "_Pricing not available._"

    if is_multiday:
        lines.append("| Option | Price |")
        lines.append("|--------|-------|")
        for p in pricing['pricing']:
            lines.append(f"| {p['name']} | ${p['amount']:,.0f} |")
    else:
        # Day tour - simpler format
        for p in pricing['pricing']:
            lines.append(f"**{p['name']}:** ${p['amount']:,.0f}")

    if pricing.get('deposit'):
        lines.append("")
        lines.append(f"*Deposit: ${pricing['deposit']['amount']:,.0f}*")

    return '\n'.join(lines)


def format_schedule_section(schedule: dict, is_multiday: bool = True) -> str:
    """Format 2026 schedule section."""
    # Always include markers for multi-day tours so sync can fill them in later
    if not is_multiday:
        return ""

    lines = ["<!-- ARCTIC_SYNC:schedule -->"]
    lines.append("## 2026 Schedule\n")

    def format_date_row(d):
        start = d['start_date']
        spots = d.get('spots_available', '?')
        total = d.get('spots_total', '?')
        status = "Available" if spots and spots > 0 else "Full"
        return f"| {start} | {spots}/{total} | {status} |"

    has_dates = schedule and schedule.get('total', 0) > 0

    if has_dates and schedule.get('spring'):
        lines.append("### Spring Season")
        lines.append("| Date | Spots | Status |")
        lines.append("|------|-------|--------|")
        for d in schedule['spring']:
            lines.append(format_date_row(d))
        lines.append("")

    if has_dates and schedule.get('fall'):
        lines.append("### Fall Season")
        lines.append("| Date | Spots | Status |")
        lines.append("|------|-------|--------|")
        for d in schedule['fall']:
            lines.append(format_date_row(d))
        lines.append("")

    if not has_dates:
        lines.append("_Schedule dates coming soon. Run `sync schedule` to update._")
        lines.append("")

    lines.append("<!-- /ARCTIC_SYNC -->")
    lines.append("")

    return '\n'.join(lines)


def migrate_document(
    doc_id: str,
    master: dict,
    arctic: ArcticClient,
    dry_run: bool = False
) -> dict:
    """Migrate a single document to new template."""
    result = {
        'doc_id': doc_id,
        'status': 'pending',
        'title': master.get('outline_title', ''),
    }

    # Fetch current document
    doc = get_outline_document(doc_id)
    if not doc:
        result['status'] = 'error'
        result['error'] = 'Could not fetch document'
        return result

    current_text = doc.get('text', '')
    current_title = doc.get('title', '')

    # Get Arctic data
    arctic_id = master.get('arctic_id')
    if not arctic_id or not arctic_id.isdigit():
        result['status'] = 'skipped'
        result['reason'] = 'No Arctic ID'
        return result

    arctic_id = int(arctic_id)

    # Fetch Arctic details
    trip_details = arctic.get_trip_details(arctic_id)
    if not trip_details:
        result['status'] = 'error'
        result['error'] = f'Arctic trip {arctic_id} not found'
        return result

    pricing = arctic.get_trip_pricing_summary(arctic_id)
    is_multiday = master.get('is_multiday', '').upper() == 'YES'

    # Get schedule for multi-day tours
    schedule = None
    if is_multiday:
        try:
            schedule = arctic.get_2026_schedule(arctic_id)
        except:
            schedule = {'total': 0, 'spring': [], 'fall': [], 'other': []}

    # Always include schedule section for multi-day (with or without dates)
    schedule_section = format_schedule_section(schedule, is_multiday=is_multiday)

    # Extract existing content
    description = extract_description_from_doc(current_text)
    itinerary = extract_itinerary_from_doc(current_text)

    # Build itinerary section
    itinerary_section = ""
    if itinerary:
        itinerary_section = f"""## Itinerary
<!-- CONTENT:itinerary -->
{itinerary}
<!-- /CONTENT -->

---
"""

    # Generate new title
    shortname = trip_details.get('shortname', f"TT{arctic_id}")
    name = trip_details.get('name', master.get('arctic_name', 'Tour'))
    new_title = generate_new_title(shortname, name)

    # Calculate group size and cutoff
    min_guests = trip_details.get('min_guests', 2)
    max_guests = trip_details.get('max_guests', 8)
    group_size = f"{min_guests}-{max_guests}" if min_guests and max_guests else "Varies"
    cutoff_days = trip_details.get('cutoff_days', 7)
    cutoff = f"{cutoff_days} days before departure" if cutoff_days else "Contact us"

    # Duration
    duration = trip_details.get('duration', '')
    duration_unit = trip_details.get('duration_unit', 'days')
    if duration:
        duration = f"{duration} {duration_unit}"
    else:
        duration = master.get('wp_title', '').split()[-1] if 'day' in master.get('wp_title', '').lower() else "Contact us"

    # Short description
    short_desc = trip_details.get('description', '')[:200] if trip_details.get('description') else "_Brief tour description._"

    # Format new document
    new_text = DOCUMENT_TEMPLATE.format(
        title=new_title,
        short_description=short_desc,
        arctic_id=arctic_id,
        wp_permalink=master.get('wp_permalink', '/tours/'),
        outline_uuid=doc_id,
        duration=duration,
        group_size=group_size,
        cutoff=cutoff,
        pricing_section=format_pricing_table(pricing, is_multiday),
        schedule_section=schedule_section,
        description=description,
        itinerary_section=itinerary_section,
        timestamp=datetime.now().strftime('%Y-%m-%d %H:%M'),
    )

    result['new_title'] = new_title
    result['has_pricing'] = bool(pricing.get('pricing'))
    result['has_schedule'] = bool(schedule and schedule.get('total', 0) > 0)
    result['has_itinerary'] = bool(itinerary)

    if dry_run:
        result['status'] = 'would_migrate'
        return result

    # Apply update
    try:
        update_outline_document(doc_id, title=new_title, text=new_text)
        result['status'] = 'migrated'
    except Exception as e:
        result['status'] = 'error'
        result['error'] = str(e)

    return result


def migrate_documents(dry_run: bool = False, limit: int = None):
    """Migrate all documents to new template."""
    print("=" * 60)
    print(f"MIGRATE DOCUMENTS {'(DRY RUN)' if dry_run else ''}")
    print("=" * 60)

    if not dry_run:
        print("\nCreating backup first...")
        backup_dir = backup_all_documents(verbose=False)
        print(f"Backup created: {backup_dir}\n")

    arctic = get_arctic_client()
    master_by_uuid = get_master_list_by_outline_uuid()

    print(f"Master list: {len(master_by_uuid)} tour mappings\n")

    migrated = 0
    skipped = 0
    errors = 0

    for doc_id, master in master_by_uuid.items():
        if limit and migrated >= limit:
            print(f"\n  (limit of {limit} reached)")
            break

        title = master.get('outline_title', doc_id[:8])
        result = migrate_document(doc_id, master, arctic, dry_run)

        if result['status'] in ('migrated', 'would_migrate'):
            migrated += 1
            action = '~' if dry_run else '+'
            print(f"  {action} {title}")
            if result.get('new_title'):
                print(f"      -> {result['new_title']}")
            extras = []
            if result.get('has_pricing'):
                extras.append('pricing')
            if result.get('has_schedule'):
                extras.append('schedule')
            if result.get('has_itinerary'):
                extras.append('itinerary')
            if extras:
                print(f"      [{', '.join(extras)}]")
        elif result['status'] == 'skipped':
            skipped += 1
            print(f"  - {title} ({result.get('reason', 'skipped')})")
        else:
            errors += 1
            print(f"  ! {title} - {result.get('error', 'unknown error')}")

        if not dry_run:
            time.sleep(API_DELAY_MS / 1000)

    print(f"\nResults:")
    print(f"  Migrated: {migrated}")
    print(f"  Skipped: {skipped}")
    print(f"  Errors: {errors}")


# ==========================================
# SYNC FUNCTIONS
# ==========================================

def sync_pricing(dry_run: bool = False):
    """Sync pricing from Arctic to Outline documents."""
    print("=" * 60)
    print(f"SYNC PRICING {'(DRY RUN)' if dry_run else ''}")
    print("=" * 60)

    arctic = get_arctic_client()
    master_by_uuid = get_master_list_by_outline_uuid()

    updated = 0
    errors = 0

    for doc_id, master in master_by_uuid.items():
        arctic_id = master.get('arctic_id')
        if not arctic_id or not arctic_id.isdigit():
            continue

        arctic_id = int(arctic_id)
        title = master.get('outline_title', doc_id[:8])

        # Fetch document
        doc = get_outline_document(doc_id)
        if not doc:
            continue

        text = doc.get('text', '')

        # Check if has pricing markers
        if '<!-- ARCTIC_SYNC:pricing -->' not in text:
            continue

        # Get fresh pricing
        pricing = arctic.get_trip_pricing_summary(arctic_id)
        is_multiday = master.get('is_multiday', '').upper() == 'YES'
        new_pricing = format_pricing_table(pricing, is_multiday)

        # Replace pricing section
        new_text = re.sub(
            r'<!-- ARCTIC_SYNC:pricing -->\s*## Pricing\s*(.*?)\s*<!-- /ARCTIC_SYNC -->',
            f'<!-- ARCTIC_SYNC:pricing -->\n## Pricing\n{new_pricing}\n<!-- /ARCTIC_SYNC -->',
            text,
            flags=re.DOTALL
        )

        if new_text == text:
            continue

        if dry_run:
            print(f"  ~ {title}")
            updated += 1
        else:
            try:
                update_outline_document(doc_id, text=new_text)
                print(f"  + {title}")
                updated += 1
                time.sleep(API_DELAY_MS / 1000)
            except Exception as e:
                print(f"  ! {title} - {e}")
                errors += 1

    print(f"\nUpdated: {updated}, Errors: {errors}")


def sync_schedule(dry_run: bool = False):
    """Sync 2026 schedule from Arctic to Outline documents."""
    print("=" * 60)
    print(f"SYNC SCHEDULE {'(DRY RUN)' if dry_run else ''}")
    print("=" * 60)

    arctic = get_arctic_client()
    master_by_uuid = get_master_list_by_outline_uuid()

    updated = 0
    errors = 0

    for doc_id, master in master_by_uuid.items():
        # Only multi-day tours
        if master.get('is_multiday', '').upper() != 'YES':
            continue

        arctic_id = master.get('arctic_id')
        if not arctic_id or not arctic_id.isdigit():
            continue

        arctic_id = int(arctic_id)
        title = master.get('outline_title', doc_id[:8])

        # Fetch document
        doc = get_outline_document(doc_id)
        if not doc:
            continue

        text = doc.get('text', '')

        # Check if has schedule markers
        if '<!-- ARCTIC_SYNC:schedule -->' not in text:
            continue

        # Get fresh schedule
        schedule = arctic.get_2026_schedule(arctic_id)
        new_schedule = format_schedule_section(schedule, is_multiday=True)

        # Replace schedule section
        new_text = re.sub(
            r'<!-- ARCTIC_SYNC:schedule -->\s*(.*?)\s*<!-- /ARCTIC_SYNC -->',
            new_schedule.strip(),
            text,
            flags=re.DOTALL
        )

        if new_text == text:
            continue

        if dry_run:
            print(f"  ~ {title} ({schedule.get('total', 0)} dates)")
            updated += 1
        else:
            try:
                update_outline_document(doc_id, text=new_text)
                print(f"  + {title} ({schedule.get('total', 0)} dates)")
                updated += 1
                time.sleep(API_DELAY_MS / 1000)
            except Exception as e:
                print(f"  ! {title} - {e}")
                errors += 1

    print(f"\nUpdated: {updated}, Errors: {errors}")


# ==========================================
# CLI
# ==========================================

def main():
    parser = argparse.ArgumentParser(
        description='Outline Tour Document Consolidation',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s backup                    Create backup of all documents
  %(prog)s rename --dry-run          Preview title changes
  %(prog)s rename                    Apply new titles
  %(prog)s migrate --dry-run         Preview content migration
  %(prog)s migrate --limit 5         Migrate first 5 documents
  %(prog)s migrate                   Full migration
  %(prog)s sync pricing              Update pricing from Arctic
  %(prog)s sync schedule             Update schedules from Arctic
  %(prog)s rollback <backup_name>    Restore from backup
        """
    )

    subparsers = parser.add_subparsers(dest='command', required=True)

    # Backup command
    backup_parser = subparsers.add_parser('backup', help='Backup all documents')

    # Rename command
    rename_parser = subparsers.add_parser('rename', help='Rename documents')
    rename_parser.add_argument('--dry-run', action='store_true', help='Preview without changes')
    rename_parser.add_argument('--limit', type=int, help='Limit number of renames')

    # Migrate command
    migrate_parser = subparsers.add_parser('migrate', help='Migrate to new template')
    migrate_parser.add_argument('--dry-run', action='store_true', help='Preview without changes')
    migrate_parser.add_argument('--limit', type=int, help='Limit number of migrations')

    # Sync command
    sync_parser = subparsers.add_parser('sync', help='Sync data from Arctic')
    sync_parser.add_argument('type', choices=['pricing', 'schedule'], help='What to sync')
    sync_parser.add_argument('--dry-run', action='store_true', help='Preview without changes')

    # Rollback command
    rollback_parser = subparsers.add_parser('rollback', help='Restore from backup')
    rollback_parser.add_argument('backup', help='Backup directory name or path')
    rollback_parser.add_argument('--dry-run', action='store_true', help='Preview without changes')

    args = parser.parse_args()

    # Validate API key
    if not OUTLINE_API_KEY:
        print("ERROR: OUTLINE_API_KEY not set in .env")
        sys.exit(1)

    if args.command == 'backup':
        backup_all_documents()
    elif args.command == 'rename':
        rename_documents(dry_run=args.dry_run, limit=args.limit)
    elif args.command == 'migrate':
        migrate_documents(dry_run=args.dry_run, limit=args.limit)
    elif args.command == 'sync':
        if args.type == 'pricing':
            sync_pricing(dry_run=args.dry_run)
        elif args.type == 'schedule':
            sync_schedule(dry_run=args.dry_run)
    elif args.command == 'rollback':
        restore_from_backup(args.backup, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
