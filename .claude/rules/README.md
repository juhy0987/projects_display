# projects-display BE — Development Rules

`projects-display` 백엔드(FastAPI + SQLAlchemy + SQLite) 개발 시 따라야 하는 규칙 모음입니다.

## 구성

- [01-architecture.md](01-architecture.md) — 레이어 구조 (router / service / repository / model) 와 의존성 흐름
- [02-fastapi-conventions.md](02-fastapi-conventions.md) — 라우터·의존성 주입·응답 스키마 규약
- [03-database.md](03-database.md) — SQLAlchemy / SQLite 사용 패턴과 마이그레이션 정책
- [04-testing.md](04-testing.md) — pytest 구조, 픽스처, 커버리지 기준
- [05-code-style.md](05-code-style.md) — Python 스타일, 네이밍, 주석, 커밋·브랜치 규약
- [06-workflow.md](06-workflow.md) — AI 협업 워크플로 (issue-first, commit-per-TODO, PR 자동화)

## 핵심 원칙

1. **단순함 우선** — 노션 스타일 블록 도구 수준의 규모. 과도한 추상화 금지.
2. **레이어 분리** — 라우터에는 입출력 검증과 의존성 wiring 만. 비즈니스 로직은 service / repository 로.
3. **명시적 타입** — Pydantic / 타입 힌트로 경계를 명확히. 런타임에 형태가 흔들리지 않도록.
4. **테스트 동반** — 라우터/리포지토리 변경에는 회귀 테스트를 함께 추가.

## 빠른 시작

새 기능을 추가할 때:

1. [01-architecture.md](01-architecture.md) 에서 해당 기능이 어느 레이어에 속하는지 확인
2. [02-fastapi-conventions.md](02-fastapi-conventions.md) 의 라우터 규약 적용
3. DB 접근이 필요하면 [03-database.md](03-database.md) 의 repository 패턴 사용
4. [04-testing.md](04-testing.md) 에 따라 테스트 추가
5. [05-code-style.md](05-code-style.md) 의 커밋·브랜치 규약으로 PR

새 블록 타입을 추가할 때:

1. `app/models/blocks.py` 에 Pydantic 모델 추가
2. `app/models/orm.py` 의 `content_json` 직렬화/역직렬화 경로 확인 (스키마 변경 불필요한 경우 많음)
3. `app/repositories/` 의 매핑 로직 보강
4. `app/routers/blocks.py` 에 핸들러 노출
5. `tests/` 에 케이스 추가
