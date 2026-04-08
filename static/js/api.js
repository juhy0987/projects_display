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

export async function apiCreateBlock(documentId, type, parentBlockId = null) {
  const res = await fetch(`/api/documents/${documentId}/blocks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ type, parent_block_id: parentBlockId }),
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

export async function apiMoveBlock(blockId, beforeBlockId) {
  const res = await fetch(`/api/blocks/${blockId}/position`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ before_block_id: beforeBlockId }),
  });
  if (!res.ok) throw new Error('Failed to move block');
}
