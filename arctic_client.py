#!/usr/bin/env python3
"""
Arctic Reservations API Client

Provides authenticated access to Arctic API endpoints for:
- Trip types (tours)
- Pricing levels
- Scheduled dates
- Trip availability
"""

import os
import requests
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from dotenv import load_dotenv

load_dotenv()

# Arctic API Configuration
ARCTIC_BASE_URL = "https://rimtours.arcticres.com/api/rest"
ARCTIC_USERNAME = os.getenv('ARCTIC_USERNAME', 'abwzxjtwhjlu')
ARCTIC_PASSWORD = os.getenv('ARCTIC_PASSWORD', 'DZgzeYb##BzEkazZqQr87isJ')


class ArcticClient:
    """Client for Arctic Reservations API."""

    def __init__(self, username: str = None, password: str = None):
        self.username = username or ARCTIC_USERNAME
        self.password = password or ARCTIC_PASSWORD
        self.auth = (self.username, self.password)
        self.base_url = ARCTIC_BASE_URL
        self._cache = {}

    def _request(self, endpoint: str, params: dict = None) -> Any:
        """Make authenticated GET request to Arctic API."""
        url = f"{self.base_url}/{endpoint}"

        try:
            response = requests.get(url, auth=self.auth, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            if response.status_code == 401:
                raise Exception("Arctic API authentication failed. Check credentials.")
            raise Exception(f"Arctic API error: {e}")
        except Exception as e:
            raise Exception(f"Arctic API request failed: {e}")

    def _get_entries(self, data: Any) -> List[Dict]:
        """Extract entries from API response."""
        if isinstance(data, dict) and 'entries' in data:
            return data['entries']
        elif isinstance(data, list):
            return data
        elif isinstance(data, dict):
            return [data]
        return []

    def _get_paginated(self, endpoint: str, params: dict = None) -> List[Dict]:
        """Get all entries from a paginated endpoint."""
        all_entries = []
        page = 0
        page_size = 50  # Arctic default

        while True:
            request_params = params.copy() if params else {}
            request_params['page'] = page

            data = self._request(endpoint, request_params)

            if isinstance(data, dict):
                entries = data.get('entries', [])
                total = data.get('total', 0)
            else:
                entries = data if isinstance(data, list) else []
                total = len(entries)

            all_entries.extend(entries)

            # Check if we have all entries
            if len(all_entries) >= total or len(entries) < page_size:
                break

            page += 1

        return all_entries

    # ==========================================
    # Trip Types
    # ==========================================

    def get_trip_types(self) -> List[Dict]:
        """Get all trip types (tours) with pagination."""
        if 'trip_types' in self._cache:
            return self._cache['trip_types']

        entries = self._get_paginated('triptype')
        self._cache['trip_types'] = entries
        return entries

    def get_trip_type(self, trip_id: int) -> Optional[Dict]:
        """Get a single trip type by ID."""
        try:
            data = self._request(f'triptype/{trip_id}')
            return data if isinstance(data, dict) else None
        except:
            return None

    def get_trip_types_by_id(self) -> Dict[int, Dict]:
        """Get trip types indexed by ID."""
        trip_types = self.get_trip_types()
        return {int(t['id']): t for t in trip_types if t.get('id')}

    # ==========================================
    # Pricing
    # ==========================================

    def get_pricing_levels(self) -> List[Dict]:
        """Get all pricing levels."""
        data = self._request('trip/pricinglevel')
        return self._get_entries(data)

    def get_pricing_for_trip(self, trip_id: int) -> List[Dict]:
        """Get pricing levels for a specific trip type."""
        # First try getting from triptype directly (embedded pricing)
        trip_type = self.get_trip_type(trip_id)
        if trip_type and trip_type.get('pricinglevels'):
            return trip_type['pricinglevels']

        # Fallback to separate pricing endpoint
        all_pricing = self.get_pricing_levels()
        return [p for p in all_pricing if p.get('parentid') == trip_id]

    def get_trip_pricing_summary(self, trip_id: int) -> Dict:
        """Get formatted pricing summary for a trip."""
        pricing_levels = self.get_pricing_for_trip(trip_id)

        result = {
            'trip_id': trip_id,
            'pricing': [],
            'deposit': None,
        }

        for level in pricing_levels:
            name = level.get('name', '').lower()
            amount = level.get('amount')

            if amount is None:
                continue

            # Handle string amounts like "$1275.00"
            if isinstance(amount, str):
                amount = amount.replace('$', '').replace(',', '')

            try:
                amount = float(amount)
            except:
                continue

            entry = {
                'name': level.get('name', 'Standard'),
                'amount': amount,
                'description': level.get('description', ''),
                'show_online': level.get('showonline', True),
                'is_default': level.get('default', False),
            }

            if 'deposit' in name:
                result['deposit'] = entry
            else:
                result['pricing'].append(entry)

        return result

    # ==========================================
    # Scheduled Dates
    # ==========================================

    # Multi-day business group IDs
    MULTIDAY_BUSINESS_GROUPS = [1, 3, 4, 23]  # Multi-day, Camping, Inn, MD eBike

    def get_scheduled_trips(self, year: int = None, trip_type_id: int = None, multiday_only: bool = True) -> List[Dict]:
        """
        Get scheduled trips using Arctic query syntax.

        Args:
            year: Filter to specific year (default: current year)
            trip_type_id: Filter to specific trip type
            multiday_only: Only return multi-day tours (business groups 1, 3, 4, 23)
        """
        # Build query for future, non-canceled trips
        query_parts = [
            'start.daterelative APPLY("operator", "on-or-after")',
            'canceled = false'
        ]

        if trip_type_id:
            query_parts.append(f'triptypeid = {trip_type_id}')

        if multiday_only:
            bg_list = ','.join(str(g) for g in self.MULTIDAY_BUSINESS_GROUPS)
            query_parts.append(f'businessgroupid IN ({bg_list})')

        query = ' AND '.join(query_parts)

        # Paginate through all results
        all_trips = []
        start = 0
        page_size = 100

        while True:
            params = {
                'query': query,
                'start': start,
                'number': page_size
            }

            data = self._request('trip', params=params)

            if isinstance(data, dict):
                entries = data.get('entries', [])
                total = data.get('total', 0)
            else:
                entries = data if isinstance(data, list) else []
                total = len(entries)

            # Filter by year if specified
            if year:
                entries = [e for e in entries if e.get('start', '').startswith(str(year))]

            all_trips.extend(entries)

            # Check if we have all results
            if start + page_size >= total or len(data.get('entries', [])) < page_size:
                break

            start += page_size

        return all_trips

    def get_scheduled_dates_for_trip(self, trip_type_id: int, year: int = None) -> List[Dict]:
        """Get scheduled dates for a specific trip type."""
        if year is None:
            year = datetime.now().year

        all_trips = self.get_scheduled_trips(year=year, trip_type_id=trip_type_id)

        dates = []
        for trip in all_trips:
            start_date = trip.get('start', '')
            if not start_date or not start_date.startswith(str(year)):
                continue

            dates.append({
                'trip_id': trip.get('id'),
                'start_date': start_date,
                'end_date': trip.get('end', ''),
                'status': trip.get('status'),
                'spots_available': trip.get('remainingopenings', 0),
                'spots_total': trip.get('openings', 0),
                'is_private': trip.get('isprivate', False),
            })

        return sorted(dates, key=lambda x: x['start_date'] or '')

    def get_2026_schedule(self, trip_type_id: int) -> Dict:
        """Get 2026 schedule organized by season. (Legacy - use get_full_schedule instead)"""
        return self.get_full_schedule(trip_type_id)

    def get_full_schedule(self, trip_type_id: int) -> Dict:
        """Get all future dates plus past 3 months, organized by season."""
        from datetime import datetime, timedelta

        today = datetime.now()
        three_months_ago = today - timedelta(days=90)

        # Build query for non-canceled trips from 3 months ago onwards
        query_parts = [
            f'triptypeid = {trip_type_id}',
            'canceled = false'
        ]
        query = ' AND '.join(query_parts)

        # Get trips
        all_trips = []
        start = 0
        page_size = 100

        while True:
            params = {
                'query': query,
                'start': start,
                'number': page_size
            }
            data = self._request('trip', params=params)
            entries = data.get('entries', []) if isinstance(data, dict) else []
            all_trips.extend(entries)

            if len(entries) < page_size:
                break
            start += page_size

        # Filter and organize
        future = []
        recent_past = []

        for trip in all_trips:
            start_date = trip.get('start', '')
            if not start_date:
                continue

            try:
                trip_date = datetime.strptime(start_date, '%Y-%m-%d')
            except:
                continue

            trip_info = {
                'trip_id': trip.get('id'),
                'start_date': start_date,
                'end_date': trip.get('end', ''),
                'spots_available': trip.get('remainingopenings', 0),
                'spots_total': trip.get('openings', 0),
                'guests': trip.get('guests', 0),
                'is_private': trip.get('isprivate', False),
            }

            if trip_date >= today:
                future.append(trip_info)
            elif trip_date >= three_months_ago:
                recent_past.append(trip_info)

        # Sort by date
        future.sort(key=lambda x: x['start_date'])
        recent_past.sort(key=lambda x: x['start_date'], reverse=True)

        return {
            'trip_type_id': trip_type_id,
            'future': future,
            'recent_past': recent_past,
            'total_future': len(future),
            'total_recent': len(recent_past),
        }

    # ==========================================
    # Trip Details
    # ==========================================

    def get_trip_details(self, trip_id: int) -> Optional[Dict]:
        """Get comprehensive details for a trip type."""
        trip = self.get_trip_type(trip_id)
        if not trip:
            return None

        return {
            'id': trip.get('id'),
            'name': trip.get('name'),
            'shortname': trip.get('shortname'),
            'description': trip.get('description'),
            'duration': trip.get('duration'),
            'duration_unit': trip.get('durationunit', 'days'),
            'min_guests': trip.get('minguestcount'),
            'max_guests': trip.get('maxguestcount'),
            'cutoff_days': trip.get('cutoffdays'),
            'show_online': trip.get('showonline', True),
            'active': trip.get('active', True),
        }

    # ==========================================
    # Utility Methods
    # ==========================================

    def get_shortname_map(self) -> Dict[int, str]:
        """Get mapping of trip type ID to shortname."""
        trip_types = self.get_trip_types()
        return {
            int(t['id']): t.get('shortname', f"TT{t['id']}")
            for t in trip_types if t.get('id')
        }

    def get_name_map(self) -> Dict[int, str]:
        """Get mapping of trip type ID to full name."""
        trip_types = self.get_trip_types()
        return {
            int(t['id']): t.get('name', f"Trip {t['id']}")
            for t in trip_types if t.get('id')
        }

    def clear_cache(self):
        """Clear internal cache."""
        self._cache = {}


# Singleton instance for convenience
_client = None

def get_client() -> ArcticClient:
    """Get or create singleton Arctic client."""
    global _client
    if _client is None:
        _client = ArcticClient()
    return _client


def test_connection() -> bool:
    """Test Arctic API connection."""
    try:
        client = get_client()
        trip_types = client.get_trip_types()
        print(f"Arctic API: Connected. Found {len(trip_types)} trip types.")
        return True
    except Exception as e:
        print(f"Arctic API: Connection failed - {e}")
        return False


if __name__ == "__main__":
    # Test the client
    print("Testing Arctic API client...")
    print("=" * 50)

    if test_connection():
        client = get_client()

        # Show sample data
        trip_types = client.get_trip_types()
        print(f"\nSample trip types:")
        for t in trip_types[:5]:
            print(f"  [{t.get('id')}] {t.get('shortname', 'N/A'):12} - {t.get('name', 'Unknown')}")

        # Test pricing for first trip
        if trip_types:
            first_id = int(trip_types[0]['id'])
            pricing = client.get_trip_pricing_summary(first_id)
            print(f"\nPricing for {trip_types[0].get('name')}:")
            for p in pricing['pricing']:
                print(f"  ${p['amount']:.2f} - {p['name']}")
