// TypeScript interfaces for Outline and D1 data structures

export interface Env {
  DB: D1Database;
  OUTLINE_API_URL: string;
  OUTLINE_API_KEY: string;
  OUTLINE_DAY_TOURS_DOC_ID: string;
  OUTLINE_MD_TOURS_DOC_ID: string;
}

// Outline API response types
export interface OutlineDocument {
  id: string;
  title: string;
  text: string;
  updatedAt: string;
  url: string;
}

export interface OutlineListResponse {
  data: OutlineDocument[];
}

export interface OutlineInfoResponse {
  data: OutlineDocument;
}

// Parsed tour data (extracted from Outline markdown)
export interface ParsedTour {
  tourCode: string;
  tourName: string;
  tourType: string | null;
  difficulty: string | null;
  durationDays: number | null;
  durationNights: number | null;
  region: string | null;
  seasonStart: string | null;
  seasonEnd: string | null;
  arcticId: number | null;
  description: string | null;
  meetingInfo: string | null;
  whatToBring: string | null;
  itineraryOverview: string | null;
  bookingNotes: string | null;
  wordpressUrl: string | null;
  outlineId: string;
  outlineUpdatedAt: string;
  priceRange: string | null;
  hasEbike: boolean;
  isPrivate: boolean;
  images: TourImage[];
  marketingCopy: MarketingCopy[];
}

export interface TourImage {
  imageType: string;
  imagePath: string;
  imageUrl: string | null;
  altText: string | null;
  sortOrder: number;
}

export interface MarketingCopy {
  style: string;
  description: string;
}

// D1 query result types
export interface TourRow {
  tour_code: string;
  tour_name: string;
  tour_type: string | null;
  difficulty: string | null;
  duration_days: number | null;
  region: string | null;
  arctic_id: number | null;
  outline_updated_at: string;
}

export interface SyncStats {
  totalProcessed: number;
  inserted: number;
  updated: number;
  errors: number;
  lastSync: string;
}
