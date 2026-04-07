async function fetchDocuments() {
  const response = await fetch('/api/documents');
  if (!response.ok) {
    throw new Error('Failed to fetch documents');
  }
  return response.json();
}

async function fetchDocument(documentId) {
  const response = await fetch(`/api/documents/${documentId}`);
  if (!response.ok) {
    throw new Error('Failed to fetch document');
  }
  return response.json();
}

function createTextBlock(block) {
  const template = document.getElementById('text-block-template');
  const node = template.content.firstElementChild.cloneNode(true);
  node.textContent = block.text;
  return node;
}

function createImageBlock(block) {
  const template = document.getElementById('image-block-template');
  const node = template.content.firstElementChild.cloneNode(true);
  const image = node.querySelector('.notion-image');
  const caption = node.querySelector('.notion-caption');

  image.src = block.url;
  caption.textContent = block.caption || '';

  if (!block.caption) {
    caption.remove();
  }

  return node;
}

function createContainerBlock(block) {
  const template = document.getElementById('container-block-template');
  const node = template.content.firstElementChild.cloneNode(true);
  const titleNode = node.querySelector('.container-title');
  const childrenRoot = node.querySelector('.container-children');

  if (block.title) {
    titleNode.textContent = block.title;
  } else {
    titleNode.remove();
  }

  if (block.layout === 'grid') {
    childrenRoot.classList.add('is-grid');
  }

  block.children.forEach((child) => {
    childrenRoot.appendChild(renderBlock(child));
  });

  return node;
}

function renderBlock(block) {
  switch (block.type) {
    case 'text':
      return createTextBlock(block);
    case 'image':
      return createImageBlock(block);
    case 'container':
      return createContainerBlock(block);
    default: {
      const unsupported = document.createElement('p');
      unsupported.className = 'notion-block unsupported-block';
      unsupported.textContent = `지원하지 않는 블록 타입: ${block.type}`;
      return unsupported;
    }
  }
}

function renderDocumentList(documents, onSelect) {
  const list = document.getElementById('document-list');
  list.innerHTML = '';

  documents.forEach((docInfo, index) => {
    const item = document.createElement('li');
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'document-item';
    button.textContent = docInfo.title;

    if (index === 0) {
      button.classList.add('is-active');
    }

    button.addEventListener('click', () => {
      list.querySelectorAll('.document-item').forEach((node) => node.classList.remove('is-active'));
      button.classList.add('is-active');
      onSelect(docInfo.id);
    });

    item.appendChild(button);
    list.appendChild(item);
  });
}

function renderDocument(documentPayload) {
  const pageTitle = document.getElementById('page-title');
  const pageSubtitle = document.getElementById('page-subtitle');
  const root = document.getElementById('block-root');

  pageTitle.textContent = documentPayload.title;
  pageSubtitle.textContent = documentPayload.subtitle || '';
  root.innerHTML = '';

  documentPayload.blocks.forEach((block) => {
    root.appendChild(renderBlock(block));
  });
}

async function initGallery() {
  const root = document.getElementById('block-root');

  try {
    const documents = await fetchDocuments();
    if (documents.length === 0) {
      root.innerHTML = '<p class="empty-state">문서가 없습니다.</p>';
      return;
    }

    const loadDocument = async (documentId) => {
      const payload = await fetchDocument(documentId);
      renderDocument(payload);
    };

    renderDocumentList(documents, loadDocument);
    await loadDocument(documents[0].id);
  } catch (error) {
    root.innerHTML = `<p class="error-state">문서를 불러오지 못했습니다: ${error.message}</p>`;
  }
}

window.addEventListener('DOMContentLoaded', initGallery);
