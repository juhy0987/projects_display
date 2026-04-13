// ── API helpers ──────────────────────────────────────────────────────────────

/**
 * 403 응답(권한 없음) 여부를 확인하고, 해당 시 사용자에게 안내한다.
 * 각 쓰기 API 래퍼의 에러 처리에서 사용한다.
 */
function _checkPermission(res) {
  if (res.status === 403) {
    throw new Error("로그인이 필요합니다. 우상단의 로그인 버튼을 이용해 주세요.");
  }
}

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
  _checkPermission(res);
  if (!res.ok) throw new Error('Failed to create document');
  return res.json();
}

export async function apiUpdateTitle(documentId, title) {
  const res = await fetch(`/api/documents/${documentId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  });
  _checkPermission(res);
  if (!res.ok) throw new Error('Failed to update title');
}

export async function apiDeleteDocument(documentId) {
  const res = await fetch(`/api/documents/${documentId}`, { method: 'DELETE' });
  _checkPermission(res);
  if (!res.ok) throw new Error('Failed to delete document');
}

export async function apiPatchBlock(blockId, fields) {
  const res = await fetch(`/api/blocks/${blockId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(fields),
  });
  _checkPermission(res);
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
  _checkPermission(res);
  if (!res.ok) throw new Error('Failed to create block');
  return res.json();
}

export async function apiDeleteBlock(blockId) {
  const res = await fetch(`/api/blocks/${blockId}`, { method: 'DELETE' });
  _checkPermission(res);
  if (!res.ok) throw new Error('Failed to delete block');
}

export async function apiChangeBlockType(blockId, type) {
  const res = await fetch(`/api/blocks/${blockId}/type`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ type }),
  });
  _checkPermission(res);
  if (!res.ok) throw new Error('Failed to change block type');
}

export async function apiUploadFile(file) {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch('/api/files', { method: 'POST', body: form });
  _checkPermission(res);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? '파일 업로드에 실패했습니다.');
  }
  return res.json();
}

export async function apiDeleteFile(fileId) {
  // 이미 없는 파일(404)은 정상으로 처리 — 멱등성 보장
  const res = await fetch(`/api/files/${fileId}`, { method: 'DELETE' });
  _checkPermission(res);
  if (!res.ok && res.status !== 404) throw new Error('파일 삭제에 실패했습니다.');
}

export async function apiUploadImage(file) {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch('/api/upload', { method: 'POST', body: form });
  _checkPermission(res);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? 'Failed to upload image');
  }
  return res.json();
}

export async function apiFetchUrlEmbed(url, blockId = null) {
  const body = { url };
  if (blockId !== null) body.block_id = blockId;
  const res = await fetch('/api/url-embed/fetch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  _checkPermission(res);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? 'URL 메타데이터를 가져올 수 없습니다.');
  }
  return res.json();
}

export async function apiMoveBlock(blockId, beforeBlockId) {
  const res = await fetch(`/api/blocks/${blockId}/position`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ before_block_id: beforeBlockId }),
  });
  _checkPermission(res);
  if (!res.ok) throw new Error('Failed to move block');
}

// ── Database API ──────────────────────────────────────────────────────────────

export async function apiAddDbColumn(dbBlockId, name, type = 'text', options = []) {
  const res = await fetch(`/api/database/blocks/${dbBlockId}/schema/columns`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, type, options }),
  });
  _checkPermission(res);
  if (!res.ok) throw new Error('Failed to add column');
  return res.json();
}

export async function apiUpdateDbColumn(dbBlockId, colId, patch) {
  const res = await fetch(`/api/database/blocks/${dbBlockId}/schema/columns/${colId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  });
  _checkPermission(res);
  if (!res.ok) throw new Error('Failed to update column');
}

export async function apiRemoveDbColumn(dbBlockId, colId) {
  const res = await fetch(`/api/database/blocks/${dbBlockId}/schema/columns/${colId}`, {
    method: 'DELETE',
  });
  _checkPermission(res);
  if (!res.ok) throw new Error('Failed to remove column');
}

export async function apiUpdateDbRowProperties(dbRowBlockId, properties) {
  const res = await fetch(`/api/database/blocks/${dbRowBlockId}/properties`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ properties }),
  });
  _checkPermission(res);
  if (!res.ok) throw new Error('Failed to update row properties');
}

export async function apiPatchDatabaseBlock(dbBlockId, fields) {
  const res = await fetch(`/api/database/blocks/${dbBlockId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(fields),
  });
  _checkPermission(res);
  if (!res.ok) throw new Error('Failed to patch database block');
}

// ── Notion Import API ────────────────────────────────────────────────────────

export async function apiImportNotion(file) {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch('/api/import/notion', { method: 'POST', body: form });
  _checkPermission(res);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? 'Notion import에 실패했습니다.');
  }
  return res.json();
}
