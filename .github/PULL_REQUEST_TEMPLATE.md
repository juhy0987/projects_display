## 연관 이슈
- Closes #

<!--
PR title 형식 (CI 강제):
  [카테고리#이슈번호] 제목     ← 예: [FEAT#2] 슬래시 커맨드 블록 추가 팔레트 구현
  [카테고리#이슈번호]: 제목    ← 콜론 형태도 허용

카테고리: FEAT / FIX / REFAC / DOCS / CHORE / TEST
거부 예시: [FEAT]: ... (#이슈번호 누락) / [FEAT 1]: ... (# 대신 공백) / feat#1: ... (소문자)

Linked Issue Check 통과 조건 = "머지 시 close 될 이슈(closing reference) 가
최소 1개 연결되어 있을 것". 다음 두 방법만 closing reference 로 인정됩니다:
1. PR 본문에 `Closes` / `Fixes` / `Resolves` 키워드 사용
2. PR 사이드바의 `Development` 에서 이슈 링크 시 `Will close this issue when
   merged` 옵션 체크
-->

<br>

## 배경 / 목적

- 배경:
- 목적:

<br>

## 구현 내용

- 

<br>

## 테스트

- [ ] `uv run pytest` 통과
- [ ] 로컬 서버 기동 (`uv run uvicorn main:app --reload`) 후 주요 경로 수동 확인
- [ ] (필요 시) FE 와 연동 흐름 확인

<br>

## CI / 머지 게이트 점검

> [CI 운영 규약](../docs/ci/conventions.md) 및 [Required Status Checks 단일 소스](../docs/ci/status-checks.md) 에 따라 작성합니다.

### 변경 영향 범위
- 영향 모듈 / 경로:
- 위험도(택1): `Low` / `Medium` / `High`

### Required Status Checks
- 통과 확인 대상 (PR Checks 탭에서 확인):
  - [ ] `Commit Lint`
  - [ ] `PR Title Lint`
  - [ ] `Linked Issue Check`
  - [ ] `Format Check`
  - [ ] `Test`

### 롤백 계획
- 

<br>

## TODO
- 

<br>

## 리뷰 포인트
- 중점적으로 봐야 할 부분:

<br>
