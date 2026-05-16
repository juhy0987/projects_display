# projects-display BE — Architecture Reference

`be/` 백엔드의 모듈 / 연결 관계를 프로젝트 디렉터리 트리와 같은 구조로 정리한 참조 문서입니다. 코드 주석을 대체하지 않으며, **모듈이 무엇을 하고 어디로 연결되는지** 빠르게 파악하기 위한 지도입니다.

상위 규칙은 [.claude/rules/01-architecture.md](../../.claude/rules/01-architecture.md) 가 정의합니다.

## 시스템 한 줄 요약

노션 스타일 블록 트리를 SQLite 에 저장하고 FastAPI 로 노출하는 단일 서비스. 프론트엔드(`fe/`) 가 같은 HTTP API 를 소비.

## 디렉터리 트리 (BE)

```
be/
├── main.py                    # FastAPI 앱 진입점
├── app/
│   ├── dependencies.py        # Depends 대상 (get_repository, get_current_user 등)
│   ├── auth/                  # 인증 (세션 / 토큰)
│   ├── models/
│   │   ├── blocks.py          # 도메인 Pydantic (TextBlock, ImageBlock, ContainerBlock, ...)
│   │   └── orm.py             # SQLAlchemy ORM (DocumentRow, BlockRow)
│   ├── repositories/
│   │   └── sqlite_blocks.py   # SQLiteBlockRepository
│   ├── routers/
│   │   ├── documents.py
│   │   └── blocks.py
│   └── services/              # 복합 비즈니스 로직 (선택)
├── data/                      # SQLite DB 파일 (data/blocks.sqlite3)
├── static/                    # 업로드된 이미지 등 정적 자산
├── templates/                 # Jinja2 HTML 템플릿
└── tests/                     # pytest
```

## 데이터 흐름 — 한 장 요약

```
HTTP Request
     │
     ▼
┌────────────────────────────┐
│ FastAPI Router             │
│ app/routers/{documents,    │
│              blocks}.py    │   ─ Pydantic 검증
└────────────┬───────────────┘
             │ Depends
             ▼
┌────────────────────────────┐
│ (Service) — 선택           │
│ app/services/*.py          │   ─ 여러 repo 조합 / 트랜잭션
└────────────┬───────────────┘
             │
             ▼
┌────────────────────────────┐
│ Repository                 │
│ app/repositories/          │   ─ SQLAlchemy 세션
│   sqlite_blocks.py         │   ─ ORM ↔ Pydantic 변환
└────────────┬───────────────┘
             │
             ▼
┌────────────────────────────┐
│ SQLite                     │
│ data/blocks.sqlite3        │
│   - documents              │
│   - blocks                 │
└────────────────────────────┘
```

## 핵심 테이블

| 테이블 | 컬럼 | 설명 |
|--------|------|------|
| `documents` | `id`, `title`, `subtitle` | 문서 메타 |
| `blocks` | `id`, `document_id`, `parent_block_id`, `type`, `position`, `content_json` | 블록 트리. `parent_block_id` 가 nullable 트리 구조 |

블록 타입: `text`, `image`, `container`, `divider`, `page` — `content_json` 에 타입별 페이로드 저장.

## 외부 의존성

| 외부 | 어디서 사용 | 용도 |
|------|------------|------|
| SQLite | `app/repositories/sqlite_blocks.py` | 영속 저장 |
| Pillow | 이미지 업로드 처리 | 썸네일 / 메타 |
| BeautifulSoup4 | Notion import | HTML 파싱 |
| 프론트 (`fe/`) | HTTP API consumer | `/api/...`, `/static/...` |

## 읽는 순서 (권장)

1. `main.py` — 어떤 라우터가 등록되어 있는가
2. `app/routers/documents.py` — 가장 단순한 리소스의 라우터 구조
3. `app/repositories/sqlite_blocks.py` — repository 패턴
4. `app/models/blocks.py` — 도메인 모델 / 블록 타입
5. `tests/conftest.py` — 테스트 픽스처 구성

## 문서 작성 규약

- **언어**: 한국어 본문 + 영어 기술용어
- **링크**: 마크다운 파일 위치 기준 상대경로
- **다이어그램**: ASCII (Mermaid 미사용)
- **갱신**: 패키지 구조가 바뀌면 이 문서를 같은 PR 에서 함께 갱신
