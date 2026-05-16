# projects-display BE

한국어 | (English version TBD)

> 노션 스타일 블록 문서 관리 도구의 백엔드 API.

## 개요

`projects-display` 의 백엔드. 노션 스타일의 블록 트리 (텍스트 / 이미지 / 컨테이너 / 디바이더 / 페이지) 를 SQLite 에 저장하고 FastAPI 로 노출합니다. 프론트엔드 (`fe/`) 가 HTTP API 를 소비합니다.

## 기술 스택

- Python 3.12+
- FastAPI + Pydantic v2
- SQLAlchemy 2 (sync)
- SQLite
- `uv` (의존성 관리)
- pytest

## 빠른 시작

### 사전 요구사항

- Python 3.12+
- `uv` 설치 ([https://docs.astral.sh/uv/](https://docs.astral.sh/uv/))

### 설치 / 실행

```bash
uv sync
uv run uvicorn main:app --reload
```

기본 포트는 `8000`. 프론트엔드 dev 서버 (`fe/`) 가 `/api` / `/static` 을 이 포트로 프록시합니다.

### 테스트

```bash
uv run pytest
uv run pytest -k "blocks"      # 이름 필터
uv run pytest -x --lf          # 첫 실패에서 멈춤 + 마지막 실패만
```

## 디렉터리 구조

```
be/
├── main.py                    # FastAPI 앱 진입점
├── app/
│   ├── dependencies.py        # Depends 대상
│   ├── auth/                  # 인증
│   ├── models/
│   │   ├── blocks.py          # 도메인 Pydantic
│   │   └── orm.py             # SQLAlchemy ORM
│   ├── repositories/          # 데이터 액세스
│   ├── routers/               # FastAPI 라우터
│   └── services/              # 복합 로직 (선택)
├── data/                      # SQLite DB
├── static/                    # 업로드 파일
├── templates/                 # Jinja2
├── tests/                     # pytest
└── docs/
    ├── architecture/
    ├── ci/
    └── ko/
```

자세한 구조는 [`docs/architecture/README.md`](../architecture/README.md) 참고.

## 핵심 개념

### 블록 트리

- `blocks` 테이블 — `id`, `document_id`, `parent_block_id` (nullable), `type`, `position`, `content_json`.
- `parent_block_id` 가 nullable 트리 — 루트 블록은 `null`.
- 블록 타입별 페이로드는 `content_json` (JSON) 에 저장 → 새 블록 타입 추가 시 스키마 마이그레이션 불필요.

### 레이어 분리

`routers → (services →) repositories → models → SQLite`

- 라우터는 입력 검증 + 의존성 wiring + 응답 직렬화만.
- 비즈니스 로직은 service / repository 로.

## 개발 규칙

- 코드 컨벤션: [`docs/CODE_CONVENTION.md`](../CODE_CONVENTION.md) — 들여쓰기 2칸, 쌍따옴표, 한국어 커밋 메시지 등.
- AI 협업 규칙: [`.claude/rules/`](../../.claude/rules/) — 각 영역별 6개 문서.
- CI 규약: [`docs/ci/conventions.md`](../ci/conventions.md), [`docs/ci/status-checks.md`](../ci/status-checks.md).

## 기여

- 이슈 먼저 (issue-first) → branch → commit → PR
- 커밋 메시지: `[FEAT|FIX|REFAC|DOCS|CHORE|TEST]: 한국어 변경 의도`
- 브랜치: `{카테고리}/#{이슈번호}/{요약}`
- PR 제목: `[카테고리#이슈번호] 한국어 제목`

자세한 워크플로는 [`.claude/rules/06-workflow.md`](../../.claude/rules/06-workflow.md) 참고.
