// ── API helpers ──────────────────────────────────────────────────────────────

export async function fetchDocuments() {
  const res = await fetch('/api/documents');
  if (!res.ok) throw new Error('Failed to fetch documents');
  return res.json();
}

export async function fetchDocument(documentId) {
  const res = await fetch(`/api/documents/${documentId}`);
  if (!res.ok) throw new Error('Failed to fetch document');
  return res.json();
}

export async function apiCreateDocument() {
  const res = await fetch('/api/documents', { method: 'POST' });
  if (!res.ok) throw new Error('Failed to create document');
  return res.json();
}

export async function apiUpdateTitle(documentId, title) {
  const res = await fetch(`/api/documents/${documentId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  });
  if (!res.ok) throw new Error('Failed to update title');
}

export async function apiDeleteDocument(documentId) {
  const res = await fetch(`/api/documents/${documentId}`, { method: 'DELETE' });
  if (!res.ok) throw new Error('Failed to delete document');
}

export async function apiPatchBlock(blockId, fields) {
  const res = await fetch(`/api/blocks/${blockId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(fields),
  });
  if (!res.ok) throw new Error('Failed to update block');
}

export async function apiCreateBlock(documentId, type, parentBlockId = null, targetDocumentId = null) {
  const body = { type, parent_block_id: parentBlockId };
  if (targetDocumentId !== null) body.target_document_id = targetDocumentId;
  const res = await fetch(`/api/documents/${documentId}/blocks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error('Failed to create block');
  return res.json();
}

export async function apiDeleteBlock(blockId) {
  const res = await fetch(`/api/blocks/${blockId}`, { method: 'DELETE' });
  if (!res.ok) throw new Error('Failed to delete block');
}

export async function apiChangeBlockType(blockId, type) {
  const res = await fetch(`/api/blocks/${blockId}/type`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ type }),
  });
  if (!res.ok) throw new Error('Failed to change block type');
}

export async function apiUploadImage(file) {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch('/api/upload', { method: 'POST', body: form });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? 'Failed to upload image');
  }
  return res.json();
}

export async function apiMoveBlock(blockId, beforeBlockId) {
  const res = await fetch(`/api/blocks/${blockId}/position`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ before_block_id: beforeBlockId }),
  });
  if (!res.ok) throw new Error('Failed to move block');
}

// ── Database API ──────────────────────────────────────────────────────────────

export async function apiAddDbColumn(dbBlockId, name, type = 'text', options = []) {
  const res = await fetch(`/api/database/blocks/${dbBlockId}/schema/columns`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, type, options }),
  });
  if (!res.ok) throw new Error('Failed to add column');
  return res.json();
}

export async function apiUpdateDbColumn(dbBlockId, colId, patch) {
  const res = await fetch(`/api/database/blocks/${dbBlockId}/schema/columns/${colId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  });
  if (!res.ok) throw new Error('Failed to update column');
}

export async function apiRemoveDbColumn(dbBlockId, colId) {
  const res = await fetch(`/api/database/blocks/${dbBlockId}/schema/columns/${colId}`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error('Failed to remove column');
}

export async function apiUpdateDbRowProperties(dbRowBlockId, properties) {
  const res = await fetch(`/api/database/blocks/${dbRowBlockId}/properties`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ properties }),
  });
  if (!res.ok) throw new Error('Failed to update row properties');
}

export async function apiPatchDatabaseBlock(dbBlockId, fields) {
  const res = await fetch(`/api/database/blocks/${dbBlockId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(fields),
  });
  if (!res.ok) throw new Error('Failed to patch database block');
}
