# 03. 데이터베이스 (SQLAlchemy + SQLite)

## 원칙

- **ORM 은 repository 안에서만 사용.** 라우터 / service / Pydantic 모델은 ORM 타입을 import 하지 않는다.
- repository 가 ORM ↔ Pydantic 변환 책임을 갖는다.
- 세션 수명은 요청 수명과 일치 — `Depends` 로 주입, 함수 종료 시 자동 닫힘.

## 세션 관리

```python
# app/dependencies.py
def get_repository() -> Iterator[SQLiteBlockRepository]:
  with SessionLocal() as session:
    yield SQLiteBlockRepository(session)
```

라우터:
```python
def list_blocks(
  document_id: str,
  repo: BlockRepository = Depends(get_repository),
): ...
```

## Repository 패턴

- 인터페이스(추상 Protocol/ABC) 와 구현체를 분리하면 테스트 시 in-memory 구현으로 대체하기 쉽다.
- 메서드 이름은 의도 중심: `find_block`, `list_children`, `save_block`, `delete_subtree`.
- bulk / batch 가 필요한 경우만 별도 메서드 (`save_blocks(list)`).

```python
class BlockRepository(Protocol):
  def find_block(self, block_id: str) -> Block | None: ...
  def list_children(self, parent_id: str | None) -> list[Block]: ...
  def save_block(self, block: Block) -> Block: ...
```

## 트랜잭션

- repository 메서드 1개 = 1 트랜잭션이 기본.
- 여러 repository 호출을 묶어야 하면 service 레이어에서 명시적으로 `session.begin()` 컨텍스트.
- 라우터에서 트랜잭션을 직접 다루지 않는다.

## 스키마 변경

- 현재 마이그레이션 도구 없음 — `data/blocks.sqlite3` 는 dev 데이터.
- 스키마 변경 시:
  1. `app/models/orm.py` 갱신
  2. 기존 DB 파일은 백업 후 재생성 (개발 환경 전제)
  3. PR 본문에 "스키마 변경" 명시
- 운영 데이터가 생기는 시점에 Alembic 도입 검토 — 별도 이슈로 합의 후 진행.

## JSON 컬럼 사용

`blocks.content_json` 은 블록 타입별 자유 페이로드를 담는 JSON 컬럼.

- 새 필드 추가는 마이그레이션 불필요 — Pydantic 모델만 갱신.
- 필드 제거 / 의미 변경은 기존 데이터와의 호환을 repository 변환 로직에서 처리.
- 인덱스가 필요한 필드는 JSON 안에 두지 말고 별도 컬럼으로 승격.

## 쿼리 가이드

- N+1 회피: 자식 블록을 모두 로딩해야 하면 단일 쿼리로 `document_id` 또는 `parent_block_id` 필터.
- 정렬은 DB 에서 (`ORDER BY position`) — Python 에서 재정렬 금지.
- LIKE / 풀텍스트는 SQLite FTS5 가 필요한 경우만 도입.

## 테스트 환경

- 테스트는 in-memory SQLite 또는 임시 파일 DB 사용 (`tests/conftest.py` 의 픽스처).
- 운영 DB 파일(`data/blocks.sqlite3`) 을 테스트가 건드리지 않도록 격리.
