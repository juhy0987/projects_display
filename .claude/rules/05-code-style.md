# 05. 코드 스타일

기존 `be/docs/CODE_CONVENTION.md` 의 내용을 반영하며, AI 협업 시 동일하게 적용한다.

## Python

- Python 3.12+, PEP 8 준수
- **들여쓰기: 공백 2칸** (4칸 아님)
- 최대 줄 길이: 100자 권장
- 문자열: **쌍따옴표(`"`)** 기본
- 공개 함수 / 메서드 / 클래스에 타입 힌트 필수
- f-string 우선. `%` / `.format()` 지양.

## 네이밍

| 종류 | 규칙 | 예 |
|------|------|-----|
| 변수 / 함수 | `snake_case` | `block_id`, `find_block` |
| 클래스 | `PascalCase` | `BlockRepository` |
| 상수 | `UPPER_SNAKE_CASE` | `DEFAULT_PAGE_SIZE` |
| 모듈 / 파일 | `lower_snake_case.py` | `sqlite_blocks.py` |
| 테스트 함수 | `test_<intent>` | `test_create_block_returns_201` |

## 주석 / docstring

- 코드가 명확하면 주석 금지.
- "WHAT" 이 아니라 "WHY" — 비자명한 의도 / 제약 / 워크어라운드만.
- 공개 함수는 간단한 한 줄 docstring 권장 (필요할 때만).
- 한국어 / 영어 혼용 OK — 일관성 유지.

## 함수 / 클래스

- 함수는 한 가지 일만. 50 라인 넘으면 분해.
- 파라미터는 5개 이내. 그 이상이면 dataclass / Pydantic 모델로 묶기.
- 부작용(파일 / 네트워크 / DB) 은 명시적으로 — 순수 함수 우선.

## 모듈 구조

```python
# 1. 표준 라이브러리
import json
from typing import Protocol

# 2. 서드파티
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

# 3. 내부 모듈
from app.models.blocks import Block
from app.repositories.sqlite_blocks import SQLiteBlockRepository
```

## 안티패턴

- **`from x import *`** — 금지. 명시적 import.
- **광역 try/except** — 잡힌 예외에 대해 적절한 처리 없이 `pass` 하지 않는다.
- **죽은 코드 / 주석 처리된 코드** — 즉시 삭제. git 이 기억한다.
- **magic number** — 의미 있는 상수로.
- **깊은 중첩** — early return 으로 평탄화.

## 커밋 메시지

형식: `[카테고리]: 한국어 변경 의도`

| 카테고리 | 의미 |
|----------|------|
| `FEAT` | 새 기능 |
| `FIX` | 버그 수정 |
| `REFAC` | 리팩터링 |
| `DOCS` | 문서 / 주석 |
| `CHORE` | 빌드 / 설정 / 의존성 |
| `TEST` | 테스트 추가 / 수정 |

- **이슈 번호는 커밋 메시지에 포함하지 않는다** (이슈 번호는 PR 제목/본문에만 사용)
- 영어 / 이모지 / 마침표 금지 (커밋 본문은 자유)

예:
```
[FEAT]: 컨테이너 블록 자식 정렬 보존 로직 추가
[FIX]: 슬래시 커맨드로 블록 타입 변경 시 content_json 누락 보정
[REFAC]: BlockRepository 인터페이스를 Protocol 로 정리
[DOCS]: 라우터별 OpenAPI summary 추가
```

## 브랜치 이름

`{카테고리}/#{이슈번호}/{핵심-변경-요약}`

- 카테고리: `feature` / `fix` / `refactor` / `docs` / `chore` / `test`
- 영문 소문자, 단어 구분은 하이픈, 30자 이내
- 예: `feature/#2/slash-command`, `fix/#15/image-upload-mime`

## PR 제목

`[카테고리#이슈번호] 한국어 제목`

- 카테고리: `FEAT` / `FIX` / `REFAC` / `DOCS` / `CHORE` / `TEST`
- 예: `[FEAT#2] 슬래시 커맨드 블록 추가 팔레트 구현`

CI 의 `PR Title Lint` 가 강제한다.

## 자동 포맷 / 린트

현 시점에 `ruff` / `black` 등 강제 도구는 없지만, 도입 시:
- `ruff format` — 들여쓰기 2칸 설정 유지
- `ruff check` — 안티패턴 자동 차단
- 도입 시 본 문서의 형식 규칙은 그 설정이 단일 소스가 됨.
