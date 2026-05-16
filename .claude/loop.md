# PR 피드백 순환 처리 (BE)

## 대상
현재 브랜치에 연결된 열린 PR의 CI 상태와 리뷰 코멘트를 처리한다.

## 절차
1. `gh pr view --json number,url,statusCheckRollup` 로 현재 PR 과 CI rollup 을 함께 조회
2. **CI 실패 확인 (코멘트 처리보다 우선)**
   - `statusCheckRollup` 항목 중 `conclusion == "FAILURE"` 인 GitHub Actions check_run 이 있으면, 실패 job 의 로그를 수집해 우선 복구
     - 실패 job 식별: `gh pr checks <PR번호>` 로 이름·URL 조회
     - 로그 수집: `gh run view <runId> --log-failed`
     - 원인 분석 → 코드/설정 수정 → 커밋 → 푸시
     - 푸시 직후 본 단계 종료. CI 재실행 결과는 다음 회차에서 재확인
   - `IN_PROGRESS` / `QUEUED` / `PENDING` 만 있고 FAILURE 가 없으면 코멘트 처리는 계속 진행
   - 모두 `SUCCESS` / `NEUTRAL` / `SKIPPED` 면 정상 진행
3. `gh api repos/{owner}/{repo}/pulls/{number}/comments` 로 리뷰 코멘트 수집
4. 👀 리액션이 달린 코멘트는 처리 완료로 건너뛴다
5. 새 코멘트가 없으면 "새 피드백 없음" 출력 후 종료

## 선별 기준
다음에 해당하는 피드백만 처리한다:
1. 비즈니스 로직 오류 또는 버그 가능성
2. 보안 (인증/인가, SQL 인젝션, 비밀 노출) 및 성능
3. 아키텍처 일관성 (라우터 / repository / 서비스 레이어 경계 위반)

단순 스타일 차이나 오타 지적은 제외한다.

## 처리 방식
- 의도가 명확한 피드백 → 코드 수정 + 커밋 + 푸시
- 의도가 불명확한 피드백 → PR 에 질문 코멘트, 질문 주체를 `@` 로 멘션
- 처리 완료한 코멘트에 👀 리액션 추가, Resolve conversation

## 커밋 규칙
- 메시지 형식
  - 리뷰 피드백 반영: `[FIX]: 피드백 반영, {변경 요약}`
  - CI 실패 복구: `[FIX]: CI 복구, {실패 job 이름} - {변경 요약}`
- 한국어로 작성

## 자동 중단 (CI 완료 후 2회 연속 무동작 시)

세션 종료 후 사용자 개입 없이도 idle 한 루프를 자체 정리하기 위한 단계입니다.
회차의 마지막 단계로 항상 수행합니다.

정책:
- **CI 진행 중 (pending)**: idle_streak 동결 — 증가/reset 모두 X.
- **CI 완료 + 신규 처리 대상 없음 (idle)**: idle_streak += 1. 2 도달 시 종료.
- **active**: idle_streak = 0 으로 reset.

### 1. 상태 파일
경로: `/tmp/projects-display-be-loop-state.json`

스키마:
```json
{
  "<PR번호>": {
    "idle_streak": 0,
    "last_run_at": "2026-05-16T00:00:00Z"
  }
}
```

### 2. 회차 분류

**active (카운터 0 reset)**
- CI 실패 복구 commit + push
- 리뷰 피드백 반영 commit + push
- 새 질문 코멘트 작성
- 신규 코멘트에 👀 + thread resolve (단순 동의/확인 답변뿐인 케이스는 idle)

**pending (카운터 동결)**
- `statusCheckRollup` 에 IN_PROGRESS / QUEUED / PENDING 항목이 하나라도 있고 FAILURE 없음
- 동시에 신규 처리 대상 코멘트도 없음

**idle (카운터 +1)**
- "새 피드백 없음" 출력으로 종료

판단 모호 시 active 로 분류.

### 3. 카운터 갱신 + 종료 판단
1. 상태 파일 read (없으면 빈 객체)
2. 본 PR 의 `idle_streak` 갱신
3. `last_run_at` 갱신 (ISO8601)
4. 상태 파일 write
5. `idle_streak >= 2` → 종료

### 4. 자동 종료 절차
1. `CronList` 로 활성 cron 조회
2. prompt 에 본 PR 번호가 포함된 loop cron 식별
3. 매칭된 cron 의 ID 로 `CronDelete`
4. 본 PR 상태 항목을 상태 파일에서 제거
5. 한 줄 알림 출력

### 5. 예외
- 사용자가 동일 PR 에 명시적으로 새 작업을 지시하면 자동 카운터와 무관
- 상태 파일 read/write 실패는 WARN 만 남기고 진행
