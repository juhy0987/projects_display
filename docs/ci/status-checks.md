# Required Status Checks — 단일 소스 (BE)

이 문서는 PR 머지 게이트에 사용되는 Required status check 이름의 **단일 소스(Single Source of Truth)** 입니다.
GitHub Ruleset 과 PR 템플릿은 모두 이 문서의 이름과 **토씨 단위로 일치** 해야 합니다.

## 명명 규칙

- 표의 `이름` 열에는 GitHub Ruleset 에 실제 등록된 체크 이름을 그대로 기재한다.
- 리네임 시 머지 게이트가 일시 중단되므로, 기존 체크 이름 변경은 문서 / 워크플로 / Ruleset 3곳을 같은 PR 에서 동시 갱신해야 한다.

## 현재 등록된 체크

| 이름 | 워크플로 / Job | 설명 | Required |
|------|---------------|------|----------|
| `Format Check` | `ci-quality.yml` / `format` | Python 포맷 검증 (들여쓰기 2칸 등) | Yes |
| `Test` | `ci-quality.yml` / `test` | `pytest` 실행 | Yes |
| `Commit Lint` | `ci-convention.yml` / `commit-lint` | 커밋 메시지 `[카테고리]:` 포맷 강제 | Yes |
| `PR Title Lint` | `ci-convention.yml` / `pr-title-lint` | PR 타이틀 `[카테고리#이슈번호] 제목` 엄격 강제 (PR only) | Yes |
| `Linked Issue Check` | `ci-convention.yml` / `linked-issue` | PR 에 closing reference 가 최소 1개 연결 (PR only) | Yes |

## 변경 절차

1. 이 문서를 먼저 업데이트한다.
2. 워크플로의 job name 을 문서에 맞춘다.
3. GitHub Ruleset 의 "Require status checks to pass" 목록을 문서에 맞춘다.
4. PR 본문에 변경된 체크 이름을 명시한다.

> 이름 불일치는 "머지 영구 차단" 의 가장 흔한 원인입니다. 리네임 시 세 곳을 **같은 PR** 에서 갱신하세요.
