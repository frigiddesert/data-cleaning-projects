#!/usr/bin/env python3
"""
Unified Tour Data Merger

Merges data from multiple sources:
1. Website export CSV (descriptions, pricing, logistics)
2. Extracted itineraries JSON (day-by-day details, meeting locations)

Outputs a unified JSON file organized by tour.
"""

import json
import re
import html
import pandas as pd
from pathlib import Path
from difflib import SequenceMatcher

# ==========================================
# CONFIGURATION
# ==========================================

WEBSITE_CSV = "datasources/Tours-Export-2025-September-09-2312 (1).csv"
ITINERARIES_JSON = "extracted_itineraries.json"
OUTPUT_JSON = "unified_tours.json"

# Website column mapping - maps various column names to canonical names
WEBSITE_FIELDS = {
    # Identity
    "website_id": ["ID"],
    "title": ["Title"],
    "slug": ["Slug"],
    "permalink": ["Permalink"],

    # Classification
    "tour_type": ["Tour Type"],
    "region": ["Region", "region"],
    "duration": ["Duration", "duration", "Day-Duration"],
    "season": ["Season"],
    "style": ["Style"],
    "skill_level": ["Multi-Day Skill Level", "Day Tour Skill Level", "skill_level"],

    # Content
    "subtitle": ["subtitle"],
    "short_description": ["short_description"],
    "description": ["description"],
    "special_notes": ["special_notes"],

    # Logistics
    "departs": ["departs"],
    "distance": ["distance"],
    "dates": ["dates"],

    # Pricing
    "standard_price": ["standard_price"],
    "private_price": ["private_tour_price"],
    "single_occupancy": ["single_occupancy"],
    "bike_rental": ["bike_rental"],
    "camp_rental": ["camp_rental"],
    "shuttle_fee": ["shuttle_fee"],

    # Booking
    "reservation_link": ["reservation_link"],

    # Images
    "image_url": ["Image URL"],
}


# ==========================================
# HELPER FUNCTIONS
# ==========================================

def strip_html(value):
    """Remove HTML tags and clean up text."""
    if pd.isna(value) or not str(value).strip():
        return ""
    text = str(value)
    # Remove script/style blocks
    text = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', text, flags=re.IGNORECASE | re.DOTALL)
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', ' ', text)
    # Decode HTML entities
    text = html.unescape(text)
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def normalize_name(name):
    """Normalize tour name for matching."""
    if not name:
        return ""
    # Remove special chars, lowercase
    normalized = re.sub(r'[^a-z0-9]', '', str(name).lower())
    return normalized


def get_field(row, field_options):
    """Get first non-empty value from list of column options."""
    for col in field_options:
        if col in row.index:
            val = row[col]
            if pd.notna(val) and str(val).strip():
                return str(val).strip()
    return ""


def fuzzy_match_score(name1, name2):
    """Calculate fuzzy match score between two strings."""
    if not name1 or not name2:
        return 0.0
    return SequenceMatcher(None, name1.lower(), name2.lower()).ratio()


def find_best_itinerary_match(tour_title, itineraries, threshold=0.6):
    """Find the best matching itinerary for a tour title."""
    best_match = None
    best_score = 0.0

    for itin in itineraries:
        # Try matching against both filename and extracted title
        filename = itin.get('source_file', '').replace('.doc', '').replace('.docx', '')
        title = itin.get('title', '')

        score_filename = fuzzy_match_score(tour_title, filename)
        score_title = fuzzy_match_score(tour_title, title)
        score = max(score_filename, score_title)

        if score > best_score and score >= threshold:
            best_score = score
            best_match = itin

    return best_match, best_score


def extract_images(image_url_str):
    """Extract image URLs from the pipe-delimited string."""
    if not image_url_str:
        return []
    urls = [url.strip() for url in str(image_url_str).split('|') if url.strip()]
    return urls


def parse_price(price_str):
    """Parse price string and extract numeric value."""
    if not price_str:
        return ""
    # Extract first dollar amount
    match = re.search(r'\$([0-9,]+)', str(price_str))
    if match:
        return match.group(0)
    return str(price_str).strip()


# ==========================================
# MAIN PROCESSING
# ==========================================

def load_website_data(csv_path):
    """Load and process website export CSV."""
    print(f"Loading website data from: {csv_path}")
    df = pd.read_csv(csv_path, dtype=str, encoding='utf-8-sig')
    print(f"  Loaded {len(df)} rows")

    tours = []
    for _, row in df.iterrows():
        tour = {}

        # Extract fields using mapping
        for field_name, column_options in WEBSITE_FIELDS.items():
            tour[field_name] = get_field(row, column_options)

        # Clean HTML from text fields
        tour['short_description'] = strip_html(tour['short_description'])
        tour['description'] = strip_html(tour['description'])
        tour['special_notes'] = strip_html(tour['special_notes'])

        # Parse prices
        tour['standard_price'] = parse_price(tour['standard_price'])
        tour['private_price'] = parse_price(tour['private_price'])
        tour['bike_rental'] = parse_price(tour['bike_rental'])
        tour['camp_rental'] = parse_price(tour['camp_rental'])
        tour['shuttle_fee'] = parse_price(tour['shuttle_fee'])

        # Extract images
        tour['images'] = extract_images(tour.get('image_url', ''))
        del tour['image_url']  # Remove raw field

        # Add normalized name for matching
        tour['_match_key'] = normalize_name(tour['title'])

        tours.append(tour)

    return tours


def load_itinerary_data(json_path):
    """Load extracted itineraries JSON."""
    print(f"Loading itinerary data from: {json_path}")
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    itineraries = data.get('itineraries', [])
    print(f"  Loaded {len(itineraries)} itineraries")
    return itineraries


def merge_tour_data(website_tours, itineraries):
    """Merge website tours with itinerary data."""
    print("\nMerging tour data...")

    merged_tours = []
    matched_count = 0
    unmatched_tours = []
    used_itineraries = set()

    for tour in website_tours:
        title = tour['title']

        # Find best matching itinerary
        best_match, score = find_best_itinerary_match(title, itineraries)

        merged = {
            # Identity
            "tour_name": title,
            "website_id": tour['website_id'],
            "slug": tour['slug'],
            "permalink": tour['permalink'],

            # Classification
            "tour_type": tour['tour_type'],
            "region": tour['region'],
            "duration": tour['duration'],
            "season": tour['season'],
            "style": tour['style'],
            "skill_level": tour['skill_level'],

            # Content from website
            "subtitle": tour['subtitle'],
            "short_description": tour['short_description'],
            "description": tour['description'],
            "special_notes": tour['special_notes'],

            # Logistics from website
            "departs_website": tour['departs'],
            "distance": tour['distance'],
            "scheduled_dates": tour['dates'],

            # Pricing
            "pricing": {
                "standard": tour['standard_price'],
                "private": tour['private_price'],
                "single_occupancy": tour['single_occupancy'],
                "bike_rental": tour['bike_rental'],
                "camp_rental": tour['camp_rental'],
                "shuttle_fee": tour['shuttle_fee'],
            },

            # Booking
            "reservation_link": tour['reservation_link'],

            # Images
            "images": tour['images'],

            # Itinerary data (from Word docs)
            "itinerary": None,
            "itinerary_match_score": 0.0,
            "itinerary_source": None,
        }

        # Add itinerary data if matched
        if best_match:
            matched_count += 1
            used_itineraries.add(best_match['source_file'])

            merged["itinerary_match_score"] = round(score, 3)
            merged["itinerary_source"] = best_match['source_file']

            # Meeting location from itinerary
            if best_match.get('meeting_location'):
                merged["meeting_location"] = best_match['meeting_location']

            # Tour metadata from itinerary
            merged["tour_rating"] = best_match.get('tour_rating', '')
            merged["terrain"] = best_match.get('terrain', '')
            merged["technical_difficulty"] = best_match.get('technical_difficulty', '')
            merged["altitude"] = best_match.get('altitude', '')

            # Day-by-day itinerary
            merged["itinerary"] = {
                "days": best_match.get('days', []),
                "overall_mileage": best_match.get('overall_mileage', ''),
            }
        else:
            unmatched_tours.append(title)

        merged_tours.append(merged)

    # Report unmatched itineraries (itineraries without website tours)
    unmatched_itineraries = [
        itin['source_file'] for itin in itineraries
        if itin['source_file'] not in used_itineraries
    ]

    print(f"\n  Website tours: {len(website_tours)}")
    print(f"  Itineraries matched: {matched_count}")
    print(f"  Website tours without itinerary: {len(unmatched_tours)}")
    print(f"  Itineraries without website tour: {len(unmatched_itineraries)}")

    return merged_tours, unmatched_tours, unmatched_itineraries


def main():
    print("=" * 60)
    print("UNIFIED TOUR DATA MERGER")
    print("=" * 60)

    # Load data
    website_tours = load_website_data(WEBSITE_CSV)
    itineraries = load_itinerary_data(ITINERARIES_JSON)

    # Merge
    merged_tours, unmatched_tours, unmatched_itins = merge_tour_data(
        website_tours, itineraries
    )

    # Prepare output
    output = {
        "summary": {
            "total_tours": len(merged_tours),
            "tours_with_itinerary": sum(1 for t in merged_tours if t['itinerary']),
            "tours_without_itinerary": len(unmatched_tours),
            "orphan_itineraries": len(unmatched_itins),
        },
        "tours": merged_tours,
        "unmatched": {
            "tours_without_itinerary": unmatched_tours,
            "itineraries_without_tour": unmatched_itins,
        }
    }

    # Save
    output_path = Path(OUTPUT_JSON)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n{'=' * 60}")
    print(f"Output saved to: {output_path}")
    print(f"{'=' * 60}")

    # Show summary
    print("\nSUMMARY:")
    print(f"  Total tours: {output['summary']['total_tours']}")
    print(f"  With itinerary: {output['summary']['tours_with_itinerary']}")
    print(f"  Without itinerary: {output['summary']['tours_without_itinerary']}")

    if unmatched_tours:
        print("\nTours without itinerary match:")
        for tour in unmatched_tours[:10]:
            print(f"  - {tour}")
        if len(unmatched_tours) > 10:
            print(f"  ... and {len(unmatched_tours) - 10} more")

    if unmatched_itins:
        print("\nItineraries without website tour:")
        for itin in unmatched_itins[:10]:
            print(f"  - {itin}")
        if len(unmatched_itins) > 10:
            print(f"  ... and {len(unmatched_itins) - 10} more")


if __name__ == "__main__":
    main()
