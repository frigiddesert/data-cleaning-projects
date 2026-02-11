// Outline markdown parser - extracts structured tour data

import { ParsedTour, TourImage, MarketingCopy } from './types';

/**
 * Parse an Outline tour document into structured data
 */
export function parseTourDocument(doc: { id: string; title: string; text: string; updatedAt: string }): ParsedTour | null {
  try {
    const { id, title, text, updatedAt } = doc;

    // Extract tour code and name from title
    const titleMatch = title.match(/^([A-Za-z0-9\-()]+)\s*[-–]\s*(.+)$/);
    if (!titleMatch) {
      console.warn(`Could not parse tour code from title: ${title}`);
      return null;
    }

    const tourCode = titleMatch[1].trim();
    const tourName = titleMatch[2].trim();

    // Parse all sections
    const arcticId = extractArcticId(text);
    const wordpressUrl = extractWordPressUrl(text);
    const tourDetails = extractTourDetails(text);
    const description = extractDescription(text);
    const meetingInfo = extractSection(text, 'Meeting Info');
    const whatToBring = extractSection(text, 'What to Bring');
    const itinerary = extractSection(text, 'Itinerary');
    const bookingNotes = extractSection(text, 'Booking');
    const marketingCopy = extractMarketingCopy(text);

    // Compute derived fields
    const hasEbike = /\b(ebike|e-bike)\b/i.test(title) || /\b(ebike|e-bike)\b/i.test(tourDetails.tourType || '');
    const isPrivate = /\(private\)/i.test(title) || /private/i.test(tourDetails.tourType || '');
    const priceRange = computePriceRange(tourDetails.durationDays);

    return {
      tourCode,
      tourName,
      tourType: tourDetails.tourType,
      difficulty: tourDetails.difficulty,
      durationDays: tourDetails.durationDays,
      durationNights: tourDetails.durationNights,
      region: tourDetails.region,
      seasonStart: tourDetails.seasonStart,
      seasonEnd: tourDetails.seasonEnd,
      arcticId,
      description,
      meetingInfo,
      whatToBring,
      itineraryOverview: itinerary,
      bookingNotes,
      wordpressUrl,
      outlineId: id,
      outlineUpdatedAt: updatedAt,
      priceRange,
      hasEbike,
      isPrivate,
      images: [], // TODO: Extract from image manifest or Outline content
      marketingCopy,
    };
  } catch (error) {
    console.error(`Error parsing tour document ${doc.id}:`, error);
    return null;
  }
}

/**
 * Extract Arctic ID from Reference table
 * Format: | Arctic | tt191 |
 */
function extractArcticId(text: string): number | null {
  const match = text.match(/\|\s*Arctic\s*\|\s*tt(\d+)\s*\|/i);
  return match ? parseInt(match[1], 10) : null;
}

/**
 * Extract WordPress URL from Reference table
 * Format: | WordPress | https://rimtours.com/tours/... |
 */
function extractWordPressUrl(text: string): string | null {
  const match = text.match(/\|\s*WordPress\s*\|\s*(https?:\/\/[^\s|]+)\s*\|/i);
  return match ? match[1].trim() : null;
}

/**
 * Extract tour details from <!-- SIDEBAR_SYNC --> section
 * Actual format in Outline:
 * | **Region** | Moab Area |
 * | **Duration** | 4-Day/3-Night |
 * | **Style** | Camping at Multiple Locations |
 * | **Season** | Fall, Spring |
 * | **Skill Level** | Intermediate, Moderate |
 */
function extractTourDetails(text: string): {
  tourType: string | null;
  difficulty: string | null;
  durationDays: number | null;
  durationNights: number | null;
  region: string | null;
  seasonStart: string | null;
  seasonEnd: string | null;
} {
  const result = {
    tourType: null as string | null,
    difficulty: null as string | null,
    durationDays: null as number | null,
    durationNights: null as number | null,
    region: null as string | null,
    seasonStart: null as string | null,
    seasonEnd: null as string | null,
  };

  // Extract Region (matches bold or non-bold)
  const regionMatch = text.match(/\|\s*\*?\*?Region\*?\*?\s*\|\s*([^|\n]+)\s*\|/i);
  if (regionMatch) result.region = regionMatch[1].trim();

  // Extract Style (this is the tour type)
  const styleMatch = text.match(/\|\s*\*?\*?Style\*?\*?\s*\|\s*([^|\n]+)\s*\|/i);
  if (styleMatch) result.tourType = styleMatch[1].trim();

  // Extract Skill Level (this is the difficulty)
  const skillMatch = text.match(/\|\s*\*?\*?Skill Level\*?\*?\s*\|\s*([^|\n]+)\s*\|/i);
  if (skillMatch) {
    // Take first value if multiple (e.g., "Intermediate, Moderate" -> "Intermediate")
    result.difficulty = skillMatch[1].split(',')[0].trim();
  }

  // Extract Duration (e.g., "4-Day/3-Night" or "Half Day")
  const durationMatch = text.match(/\|\s*\*?\*?Duration\*?\*?\s*\|\s*(\d+)-Day(?:\/(\d+)-Night)?\s*\|/i);
  if (durationMatch) {
    result.durationDays = parseInt(durationMatch[1], 10);
    result.durationNights = durationMatch[2] ? parseInt(durationMatch[2], 10) : result.durationDays - 1;
  } else {
    // Try matching "Half Day" or "Full Day"
    const halfDayMatch = text.match(/\|\s*\*?\*?Duration\*?\*?\s*\|\s*(Half|Full)\s+Day\s*\|/i);
    if (halfDayMatch) {
      result.durationDays = 1;
      result.durationNights = 0;
    }
  }

  // Extract Season (e.g., "Fall, Spring" or "March - November")
  const seasonListMatch = text.match(/\|\s*\*?\*?Season\*?\*?\s*\|\s*([^|\n]+)\s*\|/i);
  if (seasonListMatch) {
    const seasons = seasonListMatch[1].trim().split(/,\s*/);
    result.seasonStart = seasons[0];
    result.seasonEnd = seasons[seasons.length - 1];
  }

  return result;
}

/**
 * Extract description blockquote from top of document
 * Format: > Brief description here
 */
function extractDescription(text: string): string | null {
  const match = text.match(/^>\s*(.+?)(?:\n\n|\n##)/s);
  return match ? match[1].trim() : null;
}

/**
 * Extract a section by heading
 * Returns all content until the next heading
 */
function extractSection(text: string, heading: string): string | null {
  const regex = new RegExp(`## ${heading}\\s*\\n+([\\s\\S]*?)(?=\\n## |$)`, 'i');
  const match = text.match(regex);
  if (!match) return null;

  let content = match[1].trim();

  // Remove ARCTIC_SYNC sections (those are live data, not stored in D1)
  content = content.replace(/<!-- ARCTIC_SYNC:.*? -->[\s\S]*?<!-- \/ARCTIC_SYNC -->/g, '');

  // Remove CONTENT placeholder tags (but keep the content between them)
  content = content.replace(/<!-- CONTENT:\w+ -->\s*/g, '');
  content = content.replace(/\s*<!-- \/CONTENT -->/g, '');

  return content.trim() || null;
}

/**
 * Extract Marketing Copy Variations table
 * Format:
 * | Style | Description |
 * | **Adventure Seekers** | ... |
 */
function extractMarketingCopy(text: string): MarketingCopy[] {
  const results: MarketingCopy[] = [];

  // Find the Marketing Copy Variations section
  const sectionMatch = text.match(/## Marketing Copy Variations\s*\n+([\s\S]*?)(?=\n## |$)/i);
  if (!sectionMatch) return results;

  const tableContent = sectionMatch[1];

  // Extract rows (skip header)
  const rowRegex = /\|\s*\*\*([^*]+)\*\*\s*\|\s*([^|\n]+)\s*\|/g;
  let match;

  while ((match = rowRegex.exec(tableContent)) !== null) {
    const style = match[1].trim();
    const description = match[2]
      .replace(/<br\s*\/?>/gi, '\n')
      .replace(/\\\|/g, '|')
      .trim();

    results.push({ style, description });
  }

  return results;
}

/**
 * Compute price range based on duration
 * This is a rough heuristic - actual pricing comes from Arctic
 */
function computePriceRange(durationDays: number | null): string | null {
  if (!durationDays) return null;
  if (durationDays === 1) return '$200-500';
  if (durationDays <= 2) return '$500-1000';
  if (durationDays <= 4) return '$1000-2000';
  if (durationDays <= 5) return '$2000-3000';
  return '$3000+';
}
