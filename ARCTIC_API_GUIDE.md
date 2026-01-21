# Arctic Reservations API - Developer Guide

## Overview

The Arctic Reservations API is a REST API for accessing trip, reservation, person, and other reservation management data. This guide covers efficient data querying patterns to avoid pulling entire datasets.

**Critical Concept**: Always use query filters to retrieve only the data you need. The Arctic API contains tens or hundreds of thousands of records - pulling everything is inefficient and may hit rate limits.

---

## Table of Contents

1. [Authentication](#authentication)
2. [Query Syntax](#query-syntax)
3. [Filtering Strategies](#filtering-strategies)
4. [Pagination](#pagination)
5. [Common Query Patterns](#common-query-patterns)
6. [Code Examples](#code-examples)
7. [Best Practices](#best-practices)
8. [Troubleshooting](#troubleshooting)

---

## Authentication

### Basic Authentication

The Arctic API uses HTTP Basic Authentication:

**Python**
```python
import requests
from requests.auth import HTTPBasicAuth

base_url = "https://yourtenant.arcticres.com/api/rest"
auth = HTTPBasicAuth('your_username', 'your_password')

response = requests.get(f"{base_url}/trip", auth=auth, params={...})
```

**JavaScript/TypeScript**
```javascript
const axios = require('axios');

const auth = {
  username: 'your_username',
  password: 'your_password'
};

const response = await axios.get(`${baseURL}/trip`, {
  auth: auth,
  params: {...}
});
```

**curl**
```bash
curl -u 'username:password' \
  'https://yourtenant.arcticres.com/api/rest/trip?query=...'
```

### Credentials Management

**Never hardcode credentials in source code.** Use environment variables:

**Python**
```python
import os
arctic_username = os.environ['ARCTIC_USERNAME']
arctic_password = os.environ['ARCTIC_PASSWORD']
```

**JavaScript**
```javascript
const arctic_username = process.env.ARCTIC_USERNAME;
const arctic_password = process.env.ARCTIC_PASSWORD;
```

---

## Query Syntax

### The `query` Parameter

The Arctic API uses a **custom query language** passed via the `query` parameter. This is NOT standard REST filtering (like `filter[field]=value`).

**Base Pattern**:
```
GET /trip?query=<expression>&start=0&number=100
```

### Query Expression Syntax

#### 1. Field Comparisons
```
field OPERATOR value
```

**Operators**: `=`, `<`, `>`, `<=`, `>=`, `!=`, `IN`

**Examples**:
```
businessgroupid = 3
guests >= 4
canceled = false
triptypeid IN (1,3,5)
```

#### 2. Date Filtering with `daterelative APPLY`

For date fields (like `start`, `createdon`, `modifiedon`), use the `APPLY` syntax:

```
field.daterelative APPLY("param1", value1, "param2", value2, ...)
```

**Parameters**:
- `"operator"`: Comparison operator
  - `"on-or-after"` - Greater than or equal to
  - `"on-or-before"` - Less than or equal to
  - `"before"` - Less than
  - `"after"` - Greater than
  - `"on"` - Equals

- `"count"`: Number of days offset from today (integer)
- `"direction"`: `"past"` or `"future"` (used with `count`)

**Examples**:

```javascript
// Trips starting today or later
"start.daterelative APPLY(\"operator\", \"on-or-after\")"

// Trips starting within next 90 days
"start.daterelative APPLY(\"count\", 90, \"operator\", \"on-or-before\")"

// Trips from the past 30 days
"start.daterelative APPLY(\"count\", 30, \"direction\", \"past\", \"operator\", \"on-or-after\")"
```

#### 3. Combining Conditions

Use `AND` and `OR` to combine expressions:

```
condition1 AND condition2 AND condition3
```

**Example**:
```javascript
const query = "start.daterelative APPLY(\"operator\", \"on-or-after\") " +
              "AND start.daterelative APPLY(\"count\", 120, \"operator\", \"on-or-before\") " +
              "AND businessgroupid IN (1,3,4) " +
              "AND canceled = false";
```

---

## Filtering Strategies

### Strategy 1: Date Range Filtering

**Goal**: Get trips within a specific date range.

**Query**:
```javascript
// Trips from today through the next 120 days
const query = [
  'start.daterelative APPLY("operator", "on-or-after")',  // Today or later
  'start.daterelative APPLY("count", 120, "operator", "on-or-before")'  // Within 120 days
].join(' AND ');
```

### Strategy 2: Business Group Filtering

**Goal**: Only fetch trips from specific business groups (departments/divisions).

**Query**:
```javascript
// Only business groups 1, 3, and 4
const query = "businessgroupid IN (1,3,4)";
```

### Strategy 3: Exclude Canceled Trips

**Goal**: Filter out canceled trips.

**Query**:
```javascript
const query = "canceled = false";
```

### Strategy 4: Combine Multiple Filters

**Goal**: Get upcoming, non-canceled trips from specific business groups.

**Complete Example**:
```javascript
const query = [
  'start.daterelative APPLY("operator", "on-or-after")',
  'start.daterelative APPLY("count", 90, "operator", "on-or-before")',
  'businessgroupid IN (1,3,4)',
  'canceled = false'
].join(' AND ');
```

---

## Pagination

The Arctic API uses **offset-based pagination** with `start` and `number` parameters.

### Parameters

- `start`: Offset (0-based index of first record)
- `number`: Page size (number of records to return)

### Response Format

```json
{
  "total": 150,      // Total matching records
  "start": 0,        // Current offset
  "number": 100,     // Page size
  "count": null,     // (metadata)
  "entries": [...]   // Array of records
}
```

### Pagination Loop Pattern

**Python**
```python
def fetch_all_trips(query):
    trips = []
    start = 0
    page_size = 100

    while True:
        params = {
            'query': query,
            'start': start,
            'number': page_size
        }

        response = requests.get(f"{base_url}/trip", auth=auth, params=params)
        data = response.json()

        if not data.get('entries'):
            break

        trips.extend(data['entries'])

        # Check if we've retrieved all records
        if start + len(data['entries']) >= data.get('total', 0):
            break

        start += page_size

    return trips
```

---

## Common Query Patterns

### 1. Upcoming Trips (Next 90 Days)

**Use Case**: Fetch trips starting today through 90 days from now.

```javascript
const query = 'start.daterelative APPLY("operator", "on-or-after") ' +
              'AND start.daterelative APPLY("count", 90, "operator", "on-or-before")';

const params = { query, start: 0, number: 100 };
```

### 2. Recent Trips (Past 30 Days)

**Use Case**: Fetch trips that started in the past 30 days.

```javascript
const query = 'start.daterelative APPLY("count", 30, "direction", "past", "operator", "on-or-after")';
```

### 3. Trips by Business Group

**Use Case**: Fetch all trips from specific business groups.

```javascript
const query = 'businessgroupid IN (1,3,4)';
```

### 4. Trips with Guests

**Use Case**: Only trips that have at least one guest booked.

```javascript
const query = 'guests >= 1';
```

### 5. Active (Non-Canceled) Trips

**Use Case**: Exclude canceled trips.

```javascript
const query = 'canceled = false';
```

### 6. Combining Multiple Filters

**Use Case**: Upcoming non-canceled trips from specific business groups with guests.

```javascript
const query = [
  'start.daterelative APPLY("operator", "on-or-after")',
  'start.daterelative APPLY("count", 120, "operator", "on-or-before")',
  'businessgroupid IN (1,3,4)',
  'canceled = false',
  'guests >= 1'
].join(' AND ');
```

---

## Common Endpoints

| Endpoint | Description |
|----------|-------------|
| `/trip` | Trips/tours |
| `/trip/{id}` | Single trip by ID |
| `/triptype` | Trip types (tour definitions) |
| `/triptype/{id}` | Single trip type by ID |
| `/person` | Persons (customers, guides) |
| `/reservation` | Reservations |
| `/invoice` | Invoices |
| `/guide` | Guides |
| `/businessgroup` | Business groups |

---

## Best Practices

1. **Always Use Filters** - Never fetch all records without query filters
2. **Use Appropriate Page Sizes** - 100 records per page is recommended
3. **Implement Rate Limiting** - Add 250ms delays between requests
4. **Cache Lookup Data** - Cache person/guide lookups
5. **Handle Errors Gracefully** - Check for 401, 403, 500 errors
6. **Log Query Details** - Always log queries and result counts

---

## Quick Reference

### Query Syntax Cheat Sheet

| Operation | Syntax |
|-----------|--------|
| Equals | `field = value` |
| Not equals | `field != value` |
| Greater than | `field > value` |
| Less than | `field < value` |
| In list | `field IN (val1, val2, val3)` |
| Today or later | `field.daterelative APPLY("operator", "on-or-after")` |
| Within N days | `field.daterelative APPLY("count", N, "operator", "on-or-before")` |
| Past N days | `field.daterelative APPLY("count", N, "direction", "past", "operator", "on-or-after")` |
| Combine conditions | `condition1 AND condition2` |

---

**Last Updated**: 2026-01-20
**Version**: 1.0
