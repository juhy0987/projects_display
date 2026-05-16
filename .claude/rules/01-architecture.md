# 01. 아키텍처

## 시스템 한 줄 요약

노션 스타일 블록 트리를 SQLite 에 저장하고 FastAPI 로 노출하는 단일 서비스. 프론트엔드(`fe/`) 가 같은 HTTP API 를 소비.

## 레이어 구조

```
┌──────────────────────────────────────────────┐
│  HTTP (FastAPI routers)                      │
│  app/routers/*.py                            │
│  - 입력 검증 (Pydantic)                       │
│  - 의존성 주입 (Depends)                      │
│  - 응답 직렬화                                │
├──────────────────────────────────────────────┤
│  Service (선택)                              │
│  app/services/*.py                           │
│  - 여러 repository 조합이 필요한 비즈니스 로직 │
├──────────────────────────────────────────────┤
│  Repository                                  │
│  app/repositories/*.py                       │
│  - SQLAlchemy 세션을 통한 영속화              │
│  - ORM ↔ Pydantic 변환                       │
├──────────────────────────────────────────────┤
│  Models                                      │
│  app/models/blocks.py  ← Pydantic (도메인)   │
│  app/models/orm.py     ← SQLAlchemy (영속)   │
├──────────────────────────────────────────────┤
│  Storage: SQLite (`data/blocks.sqlite3`)     │
└──────────────────────────────────────────────┘
```

## 디렉터리 트리

```
be/
├── main.py                    # FastAPI 앱 진입점, 라우터 등록, 정적 파일
├── app/
│   ├── dependencies.py        # get_repository 등 Depends 대상
│   ├── auth/                  # 인증 (세션/토큰)
│   ├── models/
│   │   ├── blocks.py          # 도메인 Pydantic 모델
│   │   └── orm.py             # SQLAlchemy ORM (DocumentRow, BlockRow)
│   ├── repositories/
│   │   └── sqlite_blocks.py   # SQLiteBlockRepository
│   ├── routers/
│   │   ├── documents.py
│   │   └── blocks.py
│   └── services/              # 복합 로직 (선택)
├── data/                      # SQLite DB 파일
├── static/                    # 업로드된 이미지 등
├── templates/                 # Jinja2 (필요 시)
└── tests/                     # pytest
```

## 의존성 방향

상위 → 하위만 허용. 역방향 금지.

```
routers → services → repositories → models
                 ↘  repositories → models
```

라우터가 repository 를 직접 호출해도 좋다 (단순 CRUD). service 는 "여러 repository 를 조합" 하거나 "트랜잭션 경계가 필요" 할 때만 도입.

## 데이터 모델 핵심

- `documents` — `id`, `title`, `subtitle`
- `blocks` — `id`, `document_id`, `parent_block_id` (nullable, 트리), `type`, `position`, `content_json`
- `content_json` 에 블록 타입별 페이로드를 JSON 으로 저장 — 스키마 마이그레이션 없이 타입 확장 가능

블록 타입: `text`, `image`, `container`, `divider`, `page` (확장 가능).

## 확장 포인트

| 확장 종류 | 손대는 곳 |
|-----------|----------|
| 새 블록 타입 | `app/models/blocks.py` + `app/repositories/sqlite_blocks.py` 직렬화 |
| 새 리소스 API | `app/routers/<resource>.py` + 필요 시 repository |
| 외부 서비스 연동 | `app/services/<feature>.py` (HTTP/외부 SDK 격리) |
| 인증 변경 | `app/auth/` |

## 안 하기로 한 것 (Non-Goals)

- **마이크로서비스 분리** — 단일 서비스 유지.
- **메시지 큐 / 워커** — 모든 처리는 요청 컨텍스트 안에서 동기 수행.
- **다중 DB / 클러스터링** — SQLite 단일 파일.
- **GraphQL** — REST 만 사용.

이 경계를 넘는 변경은 별도 이슈로 합의 후 진행.
