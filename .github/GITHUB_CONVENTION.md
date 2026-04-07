# GitHub Convention

이 문서는 GitHub 협업 규칙의 기본 형태를 정의합니다.

## 1. 브랜치 전략

- 기본 브랜치: `main`
- 작업 브랜치 생성 후 PR로 병합
- 브랜치 이름 규칙:
  - 기능: `feat/#<issue-number>/<short-name>`
  - 버그 수정: `fix/#<issue-number>/<short-name>`
  - 문서: `docs/#<issue-number>/<short-name>`
  - 리팩터링: `refactor/#<issue-number>/<short-name>`

예시:

- `feat/#3/3d-gallery-filter`
- `fix/#7/notion-embed-url`

## 2. 커밋 메시지 컨벤션

Conventional Commits 기반:

- `[FEAT]: 새 기능`
- `[FIX]: 버그 수정`
- `[DOCS]: 문서 수정`
- `[REFAC]: 리팩터링`
- `[CHORE]: 빌드/설정 변경`
- `[TEST]: 테스트 추가/수정`

예시:

- `[FEAT]: add markdown-first project card renderer`
- `[FIX]: handle empty notion_url in gallery`

## 3. Pull Request 규칙

- Draft PR 적극 사용
- PR 제목은 커밋 컨벤션과 동일한 접두사 사용
- PR 본문 필수 항목:
  - 이슈 번호
  - 배경/목적
  - 변경 사항 요약
  - 테스트 결과
  - 리뷰 포인트
- 라벨 지정 권장
- PR 크기는 가능한 작게 유지 (권장: 300줄 내외)

PR 제목 형식
- `[FEAT#<Issue-Number>] <Title>`
- `[REFAC#<Issue-Number>] <Title>`
- `[FIX#<Issue-Number>] <Title>`
- `[CHORE#<Issue-Number>] <Title>`

예시:

- `[FEAT#8] Main router 추가`

## 4. 리뷰 규칙

- 코멘트에는 맥락/근거/대안 포함
- 블로킹 이슈는 반드시 해결 후 병합

## 5. 이슈 규칙

- 버그/기능 요청은 템플릿 사용
- 재현 단계와 기대 결과를 명확히 작성
- 담당자, 라벨, 마일스톤 지정 권장

이슈 제목 형식
- `[BUG] <Title>`
- `[FEATURE] <Title>`
- `[REFACTOR] <Title>`
- `[CHORE] <Title>`

## 6. 병합 규칙

- 충돌 해결 후 최신 `main` 기준으로 재검증
- CI 실패 시 병합 금지
- 병합 방식은 팀 합의 기준 사용 (squash 권장)
