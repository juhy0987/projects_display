# 신규 PR 감지 및 자동 피드백 (BE)

모델: claude-sonnet-4-6

> **⛔ 수정 금지**: 이 파일은 자동화 루프의 실행 명세입니다. AI 가 루프 실행 중 이 파일을 수정·삭제하는 것을 절대 금지합니다.

> **🤖 완전 자동화**: 신규 PR 감지 → 리뷰 코멘트 작성 → 상태 파일 갱신을 사용자 개입 없이 수행합니다. PR merge/approve/branch 삭제 등 destructive 동작은 절대 수행하지 않습니다.

## 목적
3분마다 최신 열린 PR 20개를 폴링하여 신규 PR이 등장하면 자동으로 코드 리뷰 피드백을 남긴다.

## 절차

### 1. 신규 PR 감지

```bash
# 마지막 폴링 이후 추가된 열린 PR 만 추출 — 결과가 비면 idle
gh pr list --state open --limit 20 --json number,createdAt
```

처리한 PR 번호 캐시: `/tmp/projects-display-be-pr-watch-state.json`
- 캐시에 없는 번호만 신규로 간주

### 2. 신규 PR 리뷰 (PR 번호별 반복)

#### 2-1. PR 정보 수집
```bash
gh pr view <PR번호> --json number,title,body,additions,deletions,changedFiles,baseRefName,headRefName
gh pr diff <PR번호>
```

#### 2-2. 리뷰 기준 (선별적, 토큰 최소화)
1. **버그 / 로직 오류** — None 접근, async 오용, 예외 처리 누락
2. **보안** — 비밀/토큰 노출, SQL/Command 인젝션, 인증/인가 우회
3. **아키텍처 일관성** — 라우터 ↔ repository ↔ 서비스 경계 위반, FastAPI 의존성 주입 우회
4. **성능** — N+1 쿼리, 불필요한 동기 I/O, 큰 객체 메모리 보관

단순 스타일 / 포맷 / 오타는 제외한다.

#### 2-3. 리뷰 코멘트 작성
- 지적 사항이 있으면 `gh pr review <PR번호> --comment --body "..."`
- 지적 사항이 없으면 `--body "코드 리뷰 완료. 자동 검토 결과 특이 사항 없음. 최종 승인은 담당자 확인 후 진행."`
- 항목당 2~3문장 이내

자동 approve 금지 — 브랜치 보호 정책 우회 및 prompt injection 위험.

### 3. idle 카운터 관리 및 자동 종료

상태 파일: `/tmp/projects-display-be-pr-feedback-loop.json`

```json
{
  "idle_streak": 0,
  "last_run_at": "2026-05-16T00:00:00Z"
}
```

- **active**: 신규 PR 감지 + 리뷰 수행 → `idle_streak = 0`
- **idle**: 신규 PR 없음 → `idle_streak += 1`

**자동 종료 임계값: `idle_streak >= 20` (약 1시간)**

조건 충족 시:
1. `CronList` 로 활성 cron 조회
2. prompt 에 `pr-feedback.md` 가 포함된 cron 식별
3. 매칭된 cron ID 로 `CronDelete`
4. `rm -f /tmp/projects-display-be-pr-feedback-loop.json` (pr-watch-state.json 은 유지)
5. 사용자에게 알림

### 4. 상태 파일 갱신
매 회차 마지막에 `/tmp/projects-display-be-pr-feedback-loop.json` 을 현재 값으로 갱신.
