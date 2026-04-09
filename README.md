# Project Manager

FastAPI + SQLite 기반의 노션 스타일 블록 페이지 관리 도구입니다.

문서를 블록 단위로 구성·편집할 수 있으며, 블록 간 트리 구조와 드래그 앤 드롭 재정렬을 지원합니다.

## 블록 타입

| 타입 | 설명 |
|------|------|
| `text` | 텍스트 문단 |
| `image` | 이미지 URL + 캡션 |
| `container` | 자식 블록을 중첩하는 레이아웃 컨테이너 |
| `divider` | 구분선 |
| `page` | 하위 페이지 링크 |

## 아키텍처

- **백엔드**: FastAPI + Pydantic v2, SQLAlchemy ORM
- **저장소**: SQLite (`data/blocks.sqlite3`)
- **프론트엔드**: Vanilla JS + Jinja2 템플릿

블록 데이터는 `documents`, `blocks` 테이블에 저장되며, `parent_block_id`를 이용해 트리 구조로 문서를 구성합니다.

## 실행 방법

```bash
uv sync
uvicorn main:app --reload
```

브라우저에서 `http://127.0.0.1:8000` 접속

앱 시작 시 DB 파일이 없으면 자동으로 생성되고, 예시 문서가 시드됩니다.

## API

### 문서

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/documents` | 문서 목록 조회 |
| `POST` | `/api/documents` | 빈 문서 생성 |
| `GET` | `/api/documents/{document_id}` | 블록 트리 포함 문서 조회 |
| `PATCH` | `/api/documents/{document_id}` | 문서 제목 수정 |
| `DELETE` | `/api/documents/{document_id}` | 문서 및 하위 블록 삭제 |
| `POST` | `/api/documents/{document_id}/blocks` | 문서에 블록 추가 |

### 블록

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `PATCH` | `/api/blocks/{block_id}` | 블록 콘텐츠 수정 |
| `PATCH` | `/api/blocks/{block_id}/position` | 블록 순서 변경 |
| `PATCH` | `/api/blocks/{block_id}/type` | 블록 타입 변경 |
| `DELETE` | `/api/blocks/{block_id}` | 블록 및 하위 블록 삭제 |

## 프로젝트 구조

```text
main.py                              # FastAPI 앱 엔트리포인트
app/
  models/
    blocks.py                        # Pydantic 블록 모델
    orm.py                           # SQLAlchemy ORM (DocumentRow, BlockRow)
  repositories/
    sqlite_blocks.py                 # 데이터 액세스 레이어
  routers/
    documents.py                     # 문서 라우터
    blocks.py                        # 블록 라우터
  dependencies.py                    # FastAPI 의존성 주입
templates/                           # Jinja2 HTML 템플릿
static/
  css/style.css
  js/
data/blocks.sqlite3                  # SQLite DB
```

## Conventions

- Code: `docs/CODE_CONVENTION.md`
- GitHub: `.github/GITHUB_CONVENTION.md`
- Contribution Guide: `CONTRIBUTING.md`
