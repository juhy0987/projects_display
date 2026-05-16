# CI 운영 규약 (BE)

저장소 거버넌스와 GitHub Actions CI 설계 규칙을 정의합니다.

관련 문서:
- [Required Status Checks 단일 소스](status-checks.md)

---

## 1. PR 머지 게이트 컨벤션

### 1.1 필수 요구사항
- **Required status checks**: 이름은 [status-checks.md](status-checks.md) 의 테이블과 완전 일치.
- **Required reviews**: 최소 1명, `Require review from Code Owners` 활성화.
- **Conversation resolution**: 모든 리뷰 코멘트 해결 후에만 머지 가능.
- **Linear history 권장**, Squash 또는 Rebase merge.

### 1.2 Ruleset 우선 원칙
Branch Protection 대신 **Repository Ruleset** 을 기본 수단으로 운영합니다.

**이유**:
- 우회 방지: Ruleset 은 admin bypass 범위를 명시적으로 제한.
- 세분화 타겟팅: 브랜치 패턴, 태그, 파일 경로별 규칙 분리.
- 감사 추적: 규칙 변경 이력이 별도 이벤트로 기록.

### 1.3 Bot/App 예외 처리
- **화이트리스트 방식**: 허용된 자동화(dependabot 등) 만 명시 예외.
- 인적 계정과 동일한 Ruleset 우회 금지 원칙 유지.
- 예외 목록은 [부록 A](#부록-a-허용된-botapp) 에서 관리.

---

## 2. CODEOWNERS 전략

### 2.1 원칙
- **SPOF 금지**: 핵심 경로는 가능하면 개인 + 팀 중복 지정.
- `.github/`, CI 워크플로, 배포 관련 경로는 반드시 CODEOWNERS 커버.
- 전역 `*` 패턴 사용 금지 (머지 병목 방지).

---

## 3. GitHub Actions CI 설계 규칙

### 3.1 워크플로 구조
CI 워크플로는 **기능별로 분리된 파일** 로 운영합니다.

- `ci-quality.yml` — 코드 품질 (`format`, `typecheck-build`, `test`)
- `ci-convention.yml` — PR / 커밋 메타데이터 형식 강제 (`commit-lint`, `pr-title-lint`, `linked-issue`)

각 job 은 **독립 병렬 실행**.

### 3.2 현재 CI Jobs

| Job | 워크플로 | 목적 | 실패 시 의미 |
|-----|---------|------|-------------|
| `Format Check` | `ci-quality.yml` | Python 포맷 (들여쓰기 2칸 등) 준수 여부 | 코드 포맷 미정리 |
| `Test` | `ci-quality.yml` | `pytest` 실행 | 로직 오류 또는 회귀 |
| `Commit Lint` | `ci-convention.yml` | 커밋 메시지 `[카테고리]:` 포맷 강제 | 컨벤션 위반 |
| `PR Title Lint` | `ci-convention.yml` | PR 타이틀 `[카테고리#이슈번호] 제목` 엄격 강제 | 컨벤션 위반 |
| `Linked Issue Check` | `ci-convention.yml` | PR 에 closing reference 가 최소 1개 연결 | closing reference 누락 |

### 3.3 Job 추가 / 변경 시 규칙
1. [status-checks.md](status-checks.md) 에 이름 먼저 등록
2. 워크플로에 job 추가 (이름은 문서와 일치)
3. Ruleset `required_status_checks` 에 등록
4. PR 템플릿 체크리스트에 추가
5. **같은 PR** 에서 4곳을 동시 갱신

### 3.4 Failure 처리
- 기본: job 실패 시 PR 머지 차단 (Required check).
- `continue-on-error: true` 사용 금지 (Required check 를 우회하게 됨).

---

## 4. 체크리스트 (PR 리뷰 시 확인)

- [ ] PR 템플릿의 CI 점검 섹션이 누락 없이 작성됨
- [ ] Required status check 이름이 [status-checks.md](status-checks.md) 와 일치
- [ ] `continue-on-error: true` 가 Required job 에 사용되지 않음
- [ ] CODEOWNERS 변경 시 대체 승인자 포함 여부 확인
- [ ] 워크플로 변경 시 문서 / Ruleset 동시 갱신 여부 확인

---

## 부록 A. 허용된 Bot/App

| 계정/App | 용도 | 허용 범위 |
|---------|------|----------|
| `dependabot[bot]` | 의존성 자동 업데이트 | `pyproject.toml` / `uv.lock` PR |
| _(추가 시 PR 로 이 표 갱신)_ | - | - |

> 이 표는 `Linked Issue Check` 워크플로 (`.github/workflows/ci-convention.yml` 의 `bot_allowlist` step) 의 화이트리스트와 동기화되어야 합니다.
