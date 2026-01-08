#!/usr/bin/env python3
"""
Consolidated Itinerary Extraction Script
Extracts structured data from Word documents (.doc and .docx)

Outputs JSON with:
- Tour metadata (meeting location, rating, terrain, difficulty, altitude)
- Per-day itinerary (miles, elevation, waypoints, camp/lodging, content)
"""

import os
import re
import json
import subprocess
from pathlib import Path

# Try to import docx, will be used for .docx files
try:
    import docx
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False
    print("Warning: python-docx not installed. Only .doc files will be processed.")

# ==========================================
# CONFIGURATION
# ==========================================
ITINERARY_FOLDERS = [
    "datasources/Itineraries/Itineraries/Old Itineraries",
    "datasources/Itineraries/Itineraries/New Itineraries",
]
OUTPUT_FILE = "extracted_itineraries.json"

# Patterns to FILTER OUT (remove from content)
FILTER_PATTERNS = [
    r"We look forward to riding with you[!.]?",
    r"Please call or e-?mail for more details\.?",
    r"Call for reservations[:\s]*\([0-9\-]+\)",
    r"\([0-9]{3}[-\s]?[0-9]{3}[-\s]?[0-9]{4}\)",  # Phone numbers like (480-967-7100)
    r"[0-9]{3}[-\.\s]?[0-9]{3}[-\.\s]?[0-9]{4}",  # Phone numbers like 480-967-7100
    r"Please make lodging arrangements in advance.*?flights\.",
    r"Cars may be safely left in our parking lot.*?location\.",
    r"If you would like to enjoy a proper breakfast.*?8:30 AM\.",
    r"What to bring.*?(?=Day|\Z)",  # "What to bring" sections at end
    r"Food\s*\n.*?(?=Day|\Z)",  # Food packing lists
]

# ==========================================
# FILE READING FUNCTIONS
# ==========================================

def read_docx(filepath):
    """Read a .docx file and return full text."""
    if not HAS_DOCX:
        return None
    try:
        doc = docx.Document(filepath)
        paragraphs = [para.text for para in doc.paragraphs if para.text.strip()]
        return '\n'.join(paragraphs)
    except Exception as e:
        print(f"  Error reading .docx {filepath}: {e}")
        return None


def read_doc(filepath):
    """Read a .doc file using antiword and return full text."""
    try:
        result = subprocess.run(
            ['antiword', filepath],
            capture_output=True,
            check=True
        )
        # Try UTF-8 first, fall back to latin-1
        try:
            return result.stdout.decode('utf-8')
        except UnicodeDecodeError:
            return result.stdout.decode('latin-1', errors='ignore')
    except FileNotFoundError:
        print("  Error: 'antiword' not installed. Install with: sudo apt install antiword")
        return None
    except subprocess.CalledProcessError as e:
        print(f"  Error reading .doc {filepath}: {e}")
        return None


def read_document(filepath):
    """Read a Word document (.doc or .docx) and return full text."""
    filepath = str(filepath)
    if filepath.lower().endswith('.docx'):
        return read_docx(filepath)
    elif filepath.lower().endswith('.doc'):
        return read_doc(filepath)
    return None


# ==========================================
# TEXT CLEANING FUNCTIONS
# ==========================================

def clean_content(text):
    """Remove unwanted content from text."""
    if not text:
        return text

    for pattern in FILTER_PATTERNS:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE | re.DOTALL)

    # Clean up excessive whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)

    return text.strip()


# ==========================================
# METADATA EXTRACTION FUNCTIONS
# ==========================================

def extract_tour_title(text):
    """Extract the tour title from the document."""
    # Usually the first non-empty line in all caps or the first heading
    lines = text.split('\n')
    for line in lines[:10]:
        line = line.strip()
        if line and len(line) > 5:
            # Check if it looks like a title (mostly uppercase or contains key words)
            if line.isupper() or 'ITINERARY' in line.upper() or 'TOUR' in line.upper():
                # Clean up the title
                title = re.sub(r'\s+', ' ', line).strip()
                return title
            # Also accept mixed case titles that are reasonably short
            if len(line) < 80 and not line.startswith('Meet') and not line.startswith('Day'):
                return line
    return None


def extract_meeting_location(text):
    """Extract meeting location - this is IMPORTANT."""
    patterns = [
        # "Meet: 9:00 AM, Rim Tours Headquarters, 1233 South Highway 191, Moab, UT"
        r"Meet[:\s]+([0-9]{1,2}:[0-9]{2}\s*[AP]\.?M\.?)[,\s]+(.+?)(?:\*|\n|$)",
        # "Meet: 8AM at Durango City Transit Center"
        r"Meet[:\s]+([0-9]{1,2}\s*[AP]\.?M\.?)\s+at\s+(.+?)(?:\*|\n|$)",
        # "Meet: 9am Durango City Transit" - time followed directly by location
        r"Meet[:\s]+([0-9]{1,2}(?::[0-9]{2})?\s*[AP]\.?M\.?)\s+([A-Z][^\n]+?)(?:\*|\n|$)",
        # "Meet at 9:00 AM at the Sleep Inn"
        r"Meet\s+at\s+([0-9]{1,2}:[0-9]{2}\s*[AP]\.?M\.?)\s+at\s+(.+?)(?:\.|,\s*\d{4}|\n)",
        # "meet: Guides pick up at 8am-9am" - flexible pickup
        r"[Mm]eet[:\s]+[Gg]uides\s+pick\s*up\s+(?:at\s+)?([0-9]{1,2}(?::[0-9]{2})?\s*[AP]\.?M\.?(?:\s*-\s*[0-9]{1,2}(?::[0-9]{2})?\s*[AP]\.?M\.?)?)",
        # Just the location without time - "Meet: at the hotel"
        r"Meet[:\s]+at\s+(.+?)(?:\.|,\s*\d{4}|\n)",
        # "Our staff will meet you in Bend, Oregon at 8:30 am"
        r"(?:staff\s+will\s+)?meet\s+you\s+in\s+(.+?)\s+at\s+([0-9]{1,2}(?::[0-9]{2})?\s*[AP]\.?M\.?)",
        # "will meet you at 8:30 am at the..."
        r"meet\s+you\s+(?:at\s+)?([0-9]{1,2}(?::[0-9]{2})?\s*[AP]\.?M\.?)\s+at\s+(?:the\s+)?(.+?)(?:\.|,|\n)",
        # "Our tour meets at Rim Tours' headquarters at 1233..."
        r"(?:tour|group)\s+meets\s+at\s+(.+?)(?:\s+at\s+[0-9]|\.|$)",
        # "Meeting Location: Grand Vista Hotel"
        r"Meeting\s+Location[:\s]+(.+?)(?:\n|$)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            groups = match.groups()
            if len(groups) == 2:
                time = groups[0].strip()
                location = groups[1].strip()
                # Clean up location - remove trailing punctuation
                location = re.sub(r'[,\.\*]+$', '', location).strip()
                return {"time": time, "location": location}
            elif len(groups) == 1:
                # Could be time only (flexible pickup) or location only
                val = groups[0].strip()
                # Check if it looks like a time
                if re.match(r'[0-9]{1,2}(?::[0-9]{2})?\s*[AP]\.?M\.?', val, re.IGNORECASE):
                    return {"time": val, "location": "Hotel pickup"}
                else:
                    location = re.sub(r'[,\.\*]+$', '', val).strip()
                    return {"time": "", "location": location}

    return None


def extract_tour_rating(text):
    """Extract tour rating/difficulty level."""
    patterns = [
        r"Tour Rating[:\s]+([^\n]+)",
        r"Rating[:\s]+([^\n]+)",
        r"Difficulty[:\s]+([^\n]+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    return ""


def extract_terrain(text):
    """Extract terrain description."""
    patterns = [
        r"Terrain[:\s]+([^\n]+)",
        r"Trail [Ss]urface[s]?[:\s]+([^\n]+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    return ""


def extract_technical_difficulty(text):
    """Extract technical difficulty level."""
    patterns = [
        r"Technical Difficulty[:\s]+([^\n]+)",
        r"Technical[:\s]+([^\n]+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    return ""


def extract_altitude(text):
    """Extract altitude/elevation range."""
    patterns = [
        r"Altitude[:\s]+([^\n]+)",
        r"Elevation[:\s]+([0-9,]+\s*(?:ft|feet|m).*?)(?:\n|$)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    return ""


def extract_overall_mileage(text):
    """Extract overall mileage range for the tour."""
    patterns = [
        r"Mil[ea]ge[:\s]+([0-9]+\s*(?:to|-)\s*[0-9]+\s*miles[^\n]*)",
        r"Mil[ea]ge[:\s]+([0-9]+\s*miles[^\n]*)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    return ""


# ==========================================
# DAY-BY-DAY EXTRACTION FUNCTIONS
# ==========================================

def extract_days(text):
    """Extract day-by-day itinerary information."""
    days = []

    # Pattern to find day markers
    day_pattern = re.compile(
        r'(?:^|\n)\s*Day\s+(\d+|[Oo]ne|[Tt]wo|[Tt]hree|[Ff]our|[Ff]ive|[Ss]ix|[Ss]even)[:\s\-]',
        re.IGNORECASE | re.MULTILINE
    )

    # Word to number mapping
    word_to_num = {
        'one': '1', 'two': '2', 'three': '3', 'four': '4',
        'five': '5', 'six': '6', 'seven': '7'
    }

    matches = list(day_pattern.finditer(text))

    if not matches:
        return days

    # Group by day number to handle duplicates (summary + detailed sections)
    day_sections = {}

    for i, match in enumerate(matches):
        day_num = match.group(1).lower()
        day_num = word_to_num.get(day_num, day_num)

        # Get content until next day marker or end
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[start:end].strip()

        # Store the longest version for each day
        if day_num not in day_sections or len(content) > len(day_sections[day_num]):
            day_sections[day_num] = content

    # Process each day's content
    for day_num in sorted(day_sections.keys(), key=lambda x: int(x) if x.isdigit() else 99):
        content = day_sections[day_num]

        day_data = {
            "day": day_num,
            "miles": extract_day_miles(content),
            "elevation": extract_day_elevation(content),
            "trails_waypoints": extract_trails_waypoints(content),
            "camp_lodging": extract_camp_lodging(content),
            "meals": extract_meals(content),
            "content": clean_day_content(content)
        }

        days.append(day_data)

    return days


def extract_day_miles(text):
    """Extract mileage for a specific day."""
    patterns = [
        # "Ride: 14-18 miles"
        r"Ride[:\s]+([0-9]+(?:\s*-\s*[0-9]+)?)\s*miles",
        # "Miles: 15-20"
        r"Miles[:\s]+([0-9]+(?:\s*-\s*[0-9]+)?)",
        # "Mileage: 15-20 miles"
        r"Mil[ea]ge[:\s]+([0-9]+(?:\s*-\s*[0-9]+)?)\s*miles",
        # "Approximate milage/elevation: 14-18 miles"
        r"[Aa]pproximate\s+mil[ea]ge.*?([0-9]+(?:\s*-\s*[0-9]+)?)\s*miles",
        # Inline "23-30 miles"
        r"([0-9]+\s*-\s*[0-9]+)\s*miles",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    return ""


def extract_day_elevation(text):
    """Extract elevation gain for a specific day."""
    patterns = [
        # "^2190-2340ft" or "2190-2340ft gain"
        r"[\^]?([0-9,]+(?:\s*-\s*[0-9,]+)?)\s*(?:ft|feet|')\s*(?:gain|climb)?",
        # "elevation: 2000ft"
        r"elevation[:\s]+([0-9,]+(?:\s*-\s*[0-9,]+)?)\s*(?:ft|feet)",
        # "(667-713m)" - meters
        r"\(([0-9]+(?:\s*-\s*[0-9]+)?m)\)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    return ""


def extract_trails_waypoints(text):
    """Extract trail names and waypoints."""
    patterns = [
        # "Trails/Destination: Brown's Ranch Trailhead"
        r"Trails?/Destination[:\s]+([^\n]+)",
        # "Destination: ..."
        r"Destination[:\s]+([^\n]+)",
        # "Trail: ..."
        r"Trail[:\s]+([^\n]+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    return ""


def extract_camp_lodging(text):
    """Extract camp or lodging information."""
    patterns = [
        r"Camp[:\s]+([^\n]+)",
        r"Lodging[:\s]+([^\n]+)",
        r"Overnight[:\s]+([^\n]+)",
        r"(?:set up|make)\s+camp\s+(?:at|in)\s+([^\.\n]+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    return ""


def extract_meals(text):
    """Extract meals information for the day."""
    patterns = [
        r"Meals[:\s]+([^\n]+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    return ""


def clean_day_content(text):
    """Clean day content, removing structured data that's already extracted."""
    # Remove lines that are just structured data
    lines_to_remove = [
        r"^Ride[:\s]+.*$",
        r"^Miles[:\s]+.*$",
        r"^Mil[ea]ge[:\s]+.*$",
        r"^Meals[:\s]+.*$",
        r"^Trails?/Destination[:\s]+.*$",
        r"^Camp[:\s]+.*$",
        r"^Lodging[:\s]+.*$",
        r"^Meet[:\s]+.*$",
        r"^Arrival.*$",
    ]

    content = text
    for pattern in lines_to_remove:
        content = re.sub(pattern, '', content, flags=re.IGNORECASE | re.MULTILINE)

    # Apply general content filters
    content = clean_content(content)

    # Clean up whitespace
    content = re.sub(r'\n{2,}', '\n\n', content)
    content = content.strip()

    return content


# ==========================================
# MAIN EXTRACTION FUNCTION
# ==========================================

def extract_itinerary(filepath):
    """Extract all structured data from an itinerary document."""
    text = read_document(filepath)

    if not text:
        return None

    filename = os.path.basename(filepath)

    # Extract metadata
    result = {
        "source_file": filename,
        "source_path": str(filepath),
        "title": extract_tour_title(text),
        "meeting_location": extract_meeting_location(text),
        "tour_rating": extract_tour_rating(text),
        "terrain": extract_terrain(text),
        "technical_difficulty": extract_technical_difficulty(text),
        "altitude": extract_altitude(text),
        "overall_mileage": extract_overall_mileage(text),
        "days": extract_days(text),
        "raw_text_length": len(text),
    }

    return result


def process_all_itineraries():
    """Process all itinerary files and output to JSON."""
    all_itineraries = []
    errors = []

    # Get script directory
    script_dir = Path(__file__).parent

    for folder in ITINERARY_FOLDERS:
        folder_path = script_dir / folder

        if not folder_path.exists():
            print(f"Warning: Folder not found: {folder_path}")
            continue

        print(f"\nProcessing folder: {folder}")

        for filepath in sorted(folder_path.iterdir()):
            if filepath.suffix.lower() in ['.doc', '.docx']:
                print(f"  Processing: {filepath.name}")

                try:
                    result = extract_itinerary(filepath)

                    if result:
                        all_itineraries.append(result)
                        days_count = len(result.get('days', []))
                        print(f"    -> Extracted {days_count} days")
                    else:
                        errors.append({"file": str(filepath), "error": "Could not read file"})
                        print(f"    -> ERROR: Could not read file")

                except Exception as e:
                    errors.append({"file": str(filepath), "error": str(e)})
                    print(f"    -> ERROR: {e}")

    # Save results
    output_path = script_dir / OUTPUT_FILE
    output_data = {
        "extraction_summary": {
            "total_files_processed": len(all_itineraries) + len(errors),
            "successful": len(all_itineraries),
            "errors": len(errors),
        },
        "itineraries": all_itineraries,
        "errors": errors,
    }

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*50}")
    print(f"Extraction complete!")
    print(f"  Successful: {len(all_itineraries)}")
    print(f"  Errors: {len(errors)}")
    print(f"  Output: {output_path}")

    return output_data


if __name__ == "__main__":
    process_all_itineraries()
