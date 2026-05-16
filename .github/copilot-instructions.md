# GitHub Copilot / AI 협업 지침 (BE)

이 문서는 GitHub Copilot · Claude · Codex 등 AI 협업 도구가 본 저장소(`be/`) 에서 코드를 작성할 때 따라야 할 **단일 진입 지침** 입니다. 자세한 영역별 규칙은 [`.claude/rules/`](../.claude/rules/) 의 6개 문서에 분리되어 있습니다.

## 프로젝트 한 줄

노션 스타일 블록 트리를 SQLite 에 저장하고 FastAPI 로 노출하는 단일 백엔드 서비스. 같은 저장소 트리 위쪽의 `fe/` 가 HTTP API 를 소비합니다.

## 기술 스택

- Python 3.12+
- FastAPI + Pydantic v2
- SQLAlchemy 2 (sync) + SQLite
- `uv` (의존성)
- pytest

## 디렉터리 약도

```
be/
├── main.py                    # FastAPI 진입점
├── app/
│   ├── dependencies.py        # Depends 대상
│   ├── auth/                  # 인증
│   ├── models/                # Pydantic + SQLAlchemy ORM
│   ├── repositories/          # 데이터 액세스
│   ├── routers/               # FastAPI 라우터
│   └── services/              # 복합 로직 (선택)
├── data/                      # SQLite DB
├── static/ templates/         # 정적 자산 / Jinja2
└── tests/                     # pytest
```

자세한 아키텍처는 [`docs/architecture/README.md`](../docs/architecture/README.md).

## 작성 원칙

1. **레이어 경계 유지** — 라우터 → (service →) repository → models. 라우터에서 ORM 직접 import 금지.
2. **타입 명시** — 공개 함수 / 컴포넌트 props 에 타입 힌트 필수. `Any` 회피.
3. **테스트 동반** — 라우터 / repository 변경 시 pytest 케이스 함께.
4. **단순함 우선** — 노션 스타일 블록 도구 규모. 과한 추상화 금지.

## 코드 스타일 (요약)

- 들여쓰기: **공백 2칸**
- 문자열: **쌍따옴표**
- 줄 길이: 100자 권장
- 네이밍: 변수/함수 `snake_case`, 클래스 `PascalCase`, 상수 `UPPER_SNAKE_CASE`
- 주석: WHY 만, 코드가 명확하면 생략
- 자세한 규칙: [`.claude/rules/05-code-style.md`](../.claude/rules/05-code-style.md), [`docs/CODE_CONVENTION.md`](../docs/CODE_CONVENTION.md)

## FastAPI 컨벤션 (요약)

- `APIRouter(prefix="/api/<resource>", tags=["<resource>"])` 로 통일
- 외부 자원(DB 세션, 인증 사용자) 은 `Depends` 로 주입
- 응답 / 요청은 Pydantic 모델로 명시 (`response_model=...`)
- SQLAlchemy 가 sync 이므로 라우터는 동기 함수로 작성
- 자세한 규칙: [`.claude/rules/02-fastapi-conventions.md`](../.claude/rules/02-fastapi-conventions.md)

## Repository 패턴

- ORM 은 repository 안에서만 사용. 라우터 / service / Pydantic 은 ORM import 금지
- repository 가 ORM ↔ Pydantic 변환 책임
- 세션 수명 = 요청 수명 (`Depends` 로 주입)
- 자세한 규칙: [`.claude/rules/03-database.md`](../.claude/rules/03-database.md)

## 테스트

- `pytest` + `pytest-anyio` + `httpx`
- `tests/conftest.py` 의 픽스처 사용. 의존성은 `app.dependency_overrides` 로 교체
- 사용자 관점 / 라우터 레벨 테스트 우선
- 자세한 규칙: [`.claude/rules/04-testing.md`](../.claude/rules/04-testing.md)

## Git 워크플로

### 커밋

형식: `[카테고리]: 한국어 변경 의도`

- 카테고리: `FEAT` / `FIX` / `REFAC` / `DOCS` / `CHORE` / `TEST`
- **이슈 번호는 커밋 메시지에 포함하지 않는다** — PR 제목/본문에만 사용
- 논리적 변경 단위(TODO) 마다 즉시 커밋. 작업 끝나고 몰아서 커밋 금지

### 브랜치

`{카테고리}/#{이슈번호}/{핵심-변경-요약}` (소문자, 하이픈 구분)
예: `feature/#2/slash-command`, `fix/#15/image-upload-mime`

### PR 제목

`[카테고리#이슈번호] 한국어 제목` (CI 강제)
예: `[FEAT#2] 슬래시 커맨드 블록 추가 팔레트 구현`

### PR 본문

[`PULL_REQUEST_TEMPLATE.md`](PULL_REQUEST_TEMPLATE.md) 의 모든 섹션 작성. `Closes #<이슈번호>` 포함 필수 (CI 의 Linked Issue Check 가 강제).

## 자율 진행 / 사용자 확인 (AI 협업 한정)

자세한 규칙: [`.claude/rules/06-workflow.md`](../.claude/rules/06-workflow.md).

**자율 진행 (승인 불필요)**: 코드 / 테스트 / 의존성 변경, branch / commit / push, PR 본문 작성, lint·test 실행.

**사용자 확인 필수**: 시스템 변경 (`apt-get`, `sudo`), destructive git (`push --force`, branch 삭제, `reset --hard`), 외부 영향 (PR merge, issue close, 배포), 모호한 작업 범위.

## CI / 머지 게이트

PR 머지 게이트는 [`docs/ci/status-checks.md`](../docs/ci/status-checks.md) 가 단일 소스.

필수 통과: `Commit Lint` · `PR Title Lint` · `Linked Issue Check` · `Format Check` · `Test`.

## 안 하기로 한 것 (Non-Goals)

- 마이크로서비스 분리
- 메시지 큐 / 백그라운드 워커
- 다중 DB / 클러스터링 (SQLite 단일 파일)
- GraphQL (REST 만)

이 경계를 넘는 변경은 별도 이슈로 합의 후 진행.
