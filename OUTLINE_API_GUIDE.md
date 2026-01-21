# Outline API Integration Guide

This guide documents how to interact with the Outline Wiki API for querying, creating, modifying, and managing documents. It includes lessons learned from implementing the voice notes automation system and common pitfalls to avoid.

## Table of Contents

1. [Authentication](#authentication)
2. [Core Concepts](#core-concepts)
3. [Querying Documents](#querying-documents)
4. [Creating Documents](#creating-documents)
5. [Modifying Documents](#modifying-documents)
6. [Moving Documents](#moving-documents)
7. [File Uploads](#file-uploads)
8. [Document Organization](#document-organization)
9. [Common Gotchas](#common-gotchas)
10. [Lessons Learned](#lessons-learned)

## Authentication

All Outline API requests require a Bearer token in the `Authorization` header:

```typescript
headers: {
  'Authorization': `Bearer ${apiKey}`,
  'Content-Type': 'application/json',
}
```

Get your API key from Outline's integrations settings at `https://your-outline-instance.com/settings/integrations/new`.

## Core Concepts

### Collection vs Document

- **Collection**: A top-level workspace (contains multiple documents)
- **Document**: Individual wiki page that can have child documents
- **Parent Document**: A document that contains other documents as children

### UUIDs vs URL Slugs

⚠️ **Critical**: The Outline API requires **UUIDs**, not URL slugs!

- ❌ Wrong: `MsDdoxTn3Q` (URL slug from the document URL)
- ✅ Correct: `39478cb4-b708-4380-8944-4758403536dd` (UUID from API)

To find a document's UUID, use `documents.list` or `documents.info` API calls.

### Document States

- **Draft**: Created but not yet published; cannot be a parent for nesting other documents
- **Published**: Publicly viewable; can have child documents nested under it

## Querying Documents

### List Documents in Collection

```typescript
const response = await fetch(`${baseUrl}/api/documents.list`, {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${apiKey}`,
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    collectionId: 'collection-uuid',
    limit: 100,
    offset: 0,
  }),
});

const data = await response.json();
// Returns: { pagination: { total: number }, data: Document[] }
```

### Pagination

The API returns results in pages. Always check `pagination.total` and use `offset` to paginate:

```typescript
let allDocs = [];
let offset = 0;

while (true) {
  const { docs, total } = await fetchDocuments(100, offset);
  allDocs.push(...docs);

  if (offset + docs.length >= total) break;
  offset += 100;
}
```

### Filter by Collection

Always include `collectionId` to limit queries to a specific collection:

```typescript
body: JSON.stringify({
  collectionId: 'your-collection-uuid', // ✅ Prevents scanning entire Outline instance
  limit: 100,
  offset: 0,
})
```

**Lesson learned**: Without this filter, you'll query ALL documents in your entire Outline instance, including shared documents and other collections.

### Filter by Parent Document

To find all documents that are children of a specific parent:

```typescript
body: JSON.stringify({
  parentDocumentId: 'parent-document-uuid',
})
```

### Get Document Details

```typescript
const response = await fetch(`${baseUrl}/api/documents.info`, {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${apiKey}`,
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    id: 'document-uuid',
  }),
});

const { data } = await response.json();
// Returns: { id, title, content, createdAt, updatedAt, publishedAt, ... }
```

## Creating Documents

```typescript
const response = await fetch(`${baseUrl}/api/documents.create`, {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${apiKey}`,
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    collectionId: 'collection-uuid',
    title: 'My Document',
    content: '# My Document\n\nContent here',
    parentDocumentId: 'parent-uuid', // ✅ Optional: nest under a parent
  }),
});

const { data } = await response.json();
```

### Document Content Format

Content is stored as **Markdown**:

```markdown
# Heading 1
## Heading 2

Paragraph text here.

- List item 1
- List item 2

[Link](https://example.com)
```

### Extract Title from Content

When auto-generating titles, Outline searches for these in order:

1. H1 markdown (`# Title`)
2. First N words of content

Implement this in your code:

```typescript
function extractTitleFromContent(content: string): string {
  // Check for H1 first
  const h1Match = content.match(/^#\s+(.+)$/m);
  if (h1Match) {
    return h1Match[1].trim();
  }

  // Fall back to first 8 words
  const words = content.split(/\s+/).slice(0, 8);
  return words.join(' ');
}
```

### Title Length Validation

⚠️ **Critical**: Outline enforces a **100-character limit** on document titles.

Always validate and truncate:

```typescript
function validateTitle(title: string): string {
  const maxLength = 100;
  if (title.length > maxLength) {
    return title.substring(0, maxLength - 3) + '...';
  }
  return title;
}
```

## Modifying Documents

### Update Content

Use `documents.update` to modify an existing document:

```typescript
const response = await fetch(`${baseUrl}/api/documents.update`, {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${apiKey}`,
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    id: 'document-uuid',
    title: 'Updated Title', // ✅ Optional
    content: 'Updated content', // ✅ Optional
    append: false, // ✅ false = replace, true = append
  }),
});

const { data } = await response.json();
```

### Append vs Replace

- `append: false` (default) - Replaces entire content
- `append: true` - Adds to the end of existing content

For prepending (adding to the top), fetch the document first, then update with new content first:

```typescript
const existing = await getDocumentInfo(docId);
const newContent = `New content\n\n---\n\n${existing.content}`;
await updateDocument(docId, newContent);
```

## Moving Documents

⚠️ **Critical Lesson**: Use `documents.move`, not `documents.update` for parent changes!

### Move Under a Parent Document

```typescript
const response = await fetch(`${baseUrl}/api/documents.move`, {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${apiKey}`,
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    id: 'document-uuid',
    parentDocumentId: 'parent-document-uuid',
  }),
});

const { data } = await response.json();
```

### Move to Collection Root (Remove Parent)

```typescript
body: JSON.stringify({
  id: 'document-uuid',
  parentDocumentId: null, // ✅ Moves to collection root
})
```

### Move to Different Collection

```typescript
body: JSON.stringify({
  id: 'document-uuid',
  collectionId: 'new-collection-uuid',
})
```

### Document Ordering (Index)

To position a document at a specific index under a parent:

```typescript
body: JSON.stringify({
  id: 'document-uuid',
  parentDocumentId: 'parent-uuid',
  index: 0, // ✅ 0 = first, higher numbers = further down
})
```

## File Uploads

⚠️ **Critical**: File uploads to Outline require a **two-step process**. Direct file uploads don't work.

### Step 1: Create Attachment Record

```typescript
const response = await fetch(`${baseUrl}/api/attachments.create`, {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${apiKey}`,
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    name: 'photo.jpg',
    size: file.byteLength,
    contentType: 'image/jpeg',
  }),
});

const { data } = await response.json();
// Returns: { formData: { ... }, url: 's3-presigned-url' }
```

### Step 2: Upload to S3 with Pre-signed URL

```typescript
const formData = new FormData();

// Add all form fields from response
for (const [key, value] of Object.entries(data.formData)) {
  formData.append(key, value);
}

// ✅ CRITICAL: Append file LAST, after all other fields
formData.append('file', new Blob([fileBuffer], { type: contentType }), filename);

const uploadResponse = await fetch(data.url, {
  method: 'POST',
  body: formData,
});
```

### Complete Upload Example

```typescript
async function uploadFileToOutline(
  baseUrl: string,
  apiKey: string,
  filename: string,
  fileBuffer: Uint8Array,
  contentType: string
): Promise<{ url: string; name: string }> {
  // Step 1: Create attachment record
  const attachmentResponse = await fetch(`${baseUrl}/api/attachments.create`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${apiKey}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      name: filename,
      size: fileBuffer.byteLength,
      contentType,
    }),
  });

  if (!attachmentResponse.ok) {
    throw new Error(`Failed to create attachment: ${attachmentResponse.statusText}`);
  }

  const { data: attachmentData } = await attachmentResponse.json();

  // Step 2: Upload to S3
  const formData = new FormData();

  // Add all form fields
  for (const [key, value] of Object.entries(attachmentData.formData)) {
    formData.append(key, value);
  }

  // Add file LAST
  formData.append('file', new Blob([fileBuffer], { type: contentType }), filename);

  const uploadResponse = await fetch(attachmentData.url, {
    method: 'POST',
    body: formData,
  });

  if (!uploadResponse.ok) {
    throw new Error(`Failed to upload to S3: ${uploadResponse.statusText}`);
  }

  return {
    url: attachmentData.url.split('?')[0] + '/' + filename,
    name: filename,
  };
}
```

### Embed in Document

After uploading, reference the file in document content:

```markdown
![Photo](https://s3-url/photo.jpg)

[Download Document](https://s3-url/document.pdf)
```

## Document Organization

### Parent-Child Relationships

Documents can be nested multiple levels deep:

```
Collection (root)
├── Document A
│   ├── Document A1
│   └── Document A2
└── Document B
    └── Document B1
```

### Publishing Requirements

⚠️ **Critical**: A document must be **published** before other documents can be nested under it.

To check if a document is published:

```typescript
const doc = await getDocumentInfo(docId);
if (!doc.publishedAt) {
  // Document is a draft, publish it first
  await publishDocument(docId);
}
```

### Publishing a Document

```typescript
const response = await fetch(`${baseUrl}/api/documents.publish`, {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${apiKey}`,
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    id: 'document-uuid',
  }),
});

const { data } = await response.json();
// Returns updated document with publishedAt timestamp
```

## Common Gotchas

### 1. Using URL Slug Instead of UUID

**Problem**: API returns `id: "invalid_id"` or resource not found

**Solution**: Always use the UUID from the API response, not the URL slug:

```typescript
// ❌ Wrong
const docId = 'MsDdoxTn3Q'; // This is the URL slug

// ✅ Correct
const docId = '39478cb4-b708-4380-8944-4758403536dd'; // This is the UUID
```

### 2. Querying All Documents in Outline

**Problem**: Migration script moves tour guides, waivers, and other shared documents

**Solution**: Always include `collectionId` filter:

```typescript
body: JSON.stringify({
  collectionId: 'your-collection-uuid', // ✅ Always filter
  limit: 100,
})
```

### 3. Moving Documents to Draft Parent

**Problem**: `documents.move` returns `ok: true` but parent is never set

**Solution**: Ensure parent is published first:

```typescript
const parent = await getDocumentInfo(parentDocumentId);
if (!parent.publishedAt) {
  await publishDocument(parentDocumentId);
}

// Now move document
await moveDocument(documentId, parentDocumentId);
```

### 4. FormData Field Order

**Problem**: S3 upload fails with "Invalid FormData"

**Solution**: Always append `file` field LAST:

```typescript
const formData = new FormData();

// Add all pre-signed form fields
for (const [key, value] of Object.entries(data.formData)) {
  formData.append(key, value);
}

// Add file LAST
formData.append('file', fileBlob, filename);
```

### 5. Title Exceeds 100 Characters

**Problem**: Document creation fails with validation error

**Solution**: Always validate and truncate titles:

```typescript
const maxLength = 100;
const truncatedTitle = title.length > maxLength
  ? title.substring(0, maxLength - 3) + '...'
  : title;
```

### 6. API Changes Not Visible in UI

**Problem**: Document was updated via API but changes don't show in the web UI

**Solution**: This is a known Outline limitation (CRDT caching). Users need to refresh the page to see API changes.

## Lessons Learned

### 1. Always Validate IDs

Before using any document ID in an API call, verify it's the correct format:

```typescript
function isValidUUID(id: string): boolean {
  const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  return uuidRegex.test(id);
}
```

### 2. Implement Error Handling

The Outline API returns meaningful errors. Always log and handle them:

```typescript
if (!response.ok) {
  const error = await response.json();
  console.error(`API Error: ${error.error} - ${error.message}`);
  throw new Error(`Failed to update document: ${error.message}`);
}

const data = await response.json();
if (!data.ok) {
  console.error(`API returned not ok: ${data.error}`);
  throw new Error(`Failed to update document: ${data.error}`);
}
```

### 3. Understand Collection vs Parent Document

- **Collection**: Top-level workspace, required for `documents.create`
- **Parent Document**: Nests documents under another document, optional

A document created in a collection is not automatically under any parent. Use `parentDocumentId` to nest it.

### 4. Pagination is Essential

Large Outline instances may have thousands of documents. Always implement pagination:

```typescript
const limit = 100; // Max per request
let hasMore = true;
let offset = 0;

while (hasMore) {
  const results = await fetchDocuments(limit, offset);
  // Process results
  hasMore = offset + results.length < results.total;
  offset += limit;
}
```

### 5. Batch Operations Need Delays

When moving many documents (like 36+ in a migration), the API may rate limit. Add delays:

```typescript
for (const doc of docsToMove) {
  await moveDocument(doc.id, parentId);

  // Add small delay to avoid rate limiting
  if (docsToMove.indexOf(doc) % 10 === 0) {
    await new Promise(resolve => setTimeout(resolve, 100));
  }
}
```

### 6. Test with Small Dataset First

Before running a migration script on all 500+ documents, test with a small subset:

```typescript
// Fetch only first 10 for testing
const testDocs = await fetchDocuments(10, 0);

// Verify script logic before running on full dataset
```

### 7. Always Verify After Bulk Operations

After a migration or bulk operation, verify results:

```typescript
// After moving documents, check the results
const archived = await getArchiveChildren();
console.log(`Moved documents: ${archived.length}`);

// Spot check a few documents
for (const doc of archived.slice(0, 5)) {
  console.log(`✅ ${doc.title}`);
}
```

### 8. Keep Migration Scripts in Version Control

Always commit migration scripts with clear documentation:

```bash
git add scripts/migrate-to-archive-fixed.ts
git commit -m "Add archive migration script with proper UUID handling and published check"
```

This allows rollback and reference for future migrations.

## API Endpoints Reference

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/documents.list` | POST | List documents with filtering and pagination |
| `/documents.info` | POST | Get full details of a single document |
| `/documents.create` | POST | Create a new document |
| `/documents.update` | POST | Modify document content/title |
| `/documents.move` | POST | Move document to new parent or collection |
| `/documents.publish` | POST | Publish a draft document |
| `/attachments.create` | POST | Create attachment record for file upload |

## Testing Commands

```bash
# Check archive document status
OUTLINE_API_KEY=<key> \
OUTLINE_BASE_URL=https://outline.sandland.us \
OUTLINE_ARCHIVE_ID=<uuid> \
npx tsx scripts/check-and-publish-archive.ts

# Verify archived documents
OUTLINE_API_KEY=<key> \
OUTLINE_BASE_URL=https://outline.sandland.us \
OUTLINE_COLLECTION_ID=<uuid> \
OUTLINE_ARCHIVE_ID=<uuid> \
npx tsx scripts/verify-archive.ts

# Run migration
OUTLINE_API_KEY=<key> \
OUTLINE_BASE_URL=https://outline.sandland.us \
OUTLINE_COLLECTION_ID=<uuid> \
OUTLINE_ARCHIVE_ID=<uuid> \
npx tsx scripts/migrate-to-archive-fixed.ts
```

---

**Last Updated**: 2026-01-13
**Author**: Claude Code
**Version**: 1.0
