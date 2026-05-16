# 06. AI 작업 진행 규약

AI 협업 도구(Claude / Copilot 등) 가 본 저장소에서 작업을 진행할 때 따르는 workflow 규약입니다.
**무엇을 만드느냐** 가 아닌 **어떻게 진행하느냐** 를 정의합니다.

## 1. 이슈 먼저 (issue-first)

사용자 작업 지시가 도착하면 코드 수정 시작 전에 GitHub 이슈를 먼저 생성한다.

- 모든 작업은 GitHub 이슈로 추적 — branch / commit / PR 모두 그 이슈를 참조
- 규모가 PR 1개로 reviewable diff 안 되면 메인 이슈 + sub-issue 로 분할
- 각 sub-issue 단위로 `branch → 작업 → commit → PR` 사이클
- PR closing reference 는 sub-issue (`Closes #<sub>`)

### 예외

- 사용자가 "이슈 없이 진행해" / "단발 hotfix" 라고 명시한 경우
- 1줄 typo 수정 / 명백히 작은 chore

판단 모호 시 이슈를 만든다.

## 2. 자율 진행 — 승인 요청 최소화

쿼리의 의도가 명확하면 AI 는 사용자 승인 없이 진행한다.

**자율 진행 영역 (승인 불필요)**
- 코드 작성 / 수정 / 리팩토링 / 삭제
- 테스트 추가 / 갱신
- 새 파일 / 디렉터리 생성
- 의존성 추가 (`uv add`) — 단 신규 외부 모듈은 §4 적용
- Branch 생성, 정상 push (force-push 아닌)
- Commit 단위 결정 및 실행
- PR 본문 작성
- lint / 테스트 실행 (`uv run pytest`, `uv run ruff` 등)

**예외 영역 (반드시 사용자 확인)**

| 영역 | 예시 |
|------|------|
| 시스템 자체 변경 | `apt-get install`, `sudo systemctl`, 글로벌 환경 변경 |
| 언급 없는 destructive 권한 | `git push --force`, branch 삭제, `git reset --hard`, 무인 PR merge |
| 외부 시스템 영향 | PR merge / issue close / 배포 트리거 / 외부 API 비용 결제 |
| 모호한 작업 범위 | 사용자 의도가 다중 해석 가능한 경우 — 진행 전 구체화 질문 |

판단 모호 시 사용자 확인 쪽으로 보수 분류.

## 3. Commit-per-TODO

별다른 사용자 언급이 없으면, AI 는 작업을 **논리적 변경 단위 (TODO)** 마다 commit 한다.

- 논리 단위 완성 → **즉시 커밋** (다음 단위 시작 전)
- 큰 PR 도 reviewable diff 단위로 분할
- 각 commit 메시지는 [05-code-style.md](05-code-style.md) 의 컨벤션 준수
- 빌드 그린 유지 — 각 commit 이 컴파일 + 테스트 통과

**금지**: 작업을 모두 완료한 뒤 한 번에 몰아서 커밋.

### 예외

- 사용자가 "한 번에 묶어줘" / "squash 해줘" 명시 시 단일 commit

## 4. PR 자동 생성

작업 완료 직후 (별다른 언급 없으면) AI 는 PR 을 자동 생성한다.

- **PR 타이틀**: `[카테고리#이슈번호] 제목` (CI 강제)
- **본문**: [`PULL_REQUEST_TEMPLATE.md`](../../.github/PULL_REQUEST_TEMPLATE.md) 의 모든 섹션 채움
  - 연관 이슈 (`Closes #N`)
  - 구현 내용
  - 변경 영향 범위 + 위험도
  - 테스트 결과
  - 롤백 계획
- **이슈 링크**: 본문 또는 Development sidebar 에 closing reference 1개 이상

### 예외

- 사용자가 "이슈 없이 PR 올려줘" 또는 "이슈 먼저 만들어줘" 를 명시한 경우

## 5. 권한 사용 최소화

- 새 `Bash(...)` permission 요청은 작업 완수에 불가피한 경우에만
- 동등 효과를 낼 수 있는 기존 허용 도구를 우선 사용 (`gh`, `uv`, `git`, `make`)
- `WebFetch` / `WebSearch` 도 새 도메인은 작업 명시적 필요 시에만
- 신규 외부 의존성 추가는 §1 의 "모호 영역" 으로 간주 → 사용자 사전 확인

## 6. 이슈 / PR 분류 메타데이터

이슈 / PR 생성 시 항상 Label 부여.

| Issue prefix | Label |
|--------------|-------|
| `[FEATURE]` | `enhancement` |
| `[REFACTOR]` | `refactor` |
| `[CHORE]` | `chore` |
| `[DOCS]` | `documentation` |
| `[FIX]` | `bug` |
| `[HOTFIX]` | `bug` + `hotfix` |
| `[TEST]` | `test` |

PR 의 Label 은 그 PR 이 닫는 이슈의 Label 과 동일하게.

## 적용 흐름 (요약)

1. 의도가 명확한가? Yes → 진행 / No → 구체화 질문
2. 이슈 생성 + Label 부여 (§1, §6) — "이슈 없이 진행" 명시 시 skip
3. destructive / 시스템 / 외부 영향? Yes → 사용자 확인 / No → 진행
4. 새 권한 / 외부 의존성 필요? Yes → 사용자 확인 / No → 진행
5. 작업 진행 — 논리 단위마다 commit (§3)
6. 작업 완료 → PR 자동 생성 + Label (§4, §6) — `Closes #N`
