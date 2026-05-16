# 02. FastAPI 컨벤션

## 라우터

- 파일은 리소스 단위로 분리: `app/routers/documents.py`, `app/routers/blocks.py`.
- `APIRouter(prefix="/api/<resource>", tags=["<resource>"])` 로 prefix 통일.
- 라우터 함수명은 동작 + 리소스: `list_documents`, `create_block`, `update_block_content`.
- HTTP 메서드와 의미 맞추기:
  - `GET` — 조회, idempotent
  - `POST` — 생성 / 비-idempotent 액션
  - `PUT` / `PATCH` — 갱신 (전체 / 부분)
  - `DELETE` — 삭제

```python
from fastapi import APIRouter, Depends, HTTPException, status

router = APIRouter(prefix="/api/documents", tags=["documents"])

@router.get("/{document_id}", response_model=DocumentRead)
def get_document(
  document_id: str,
  repo: BlockRepository = Depends(get_repository),
) -> DocumentRead:
  doc = repo.find_document(document_id)
  if doc is None:
    raise HTTPException(status.HTTP_404_NOT_FOUND, "document not found")
  return doc
```

## 의존성 주입

- 모든 외부 자원(DB 세션, repository, 인증 사용자 등)은 `Depends` 로 받는다.
- `app/dependencies.py` 가 단일 진입점. 라우터 모듈에서 직접 ORM 세션 생성 금지.
- 테스트에서는 `app.dependency_overrides` 로 교체.

## 응답 / 요청 스키마

- 응답은 가능한 한 Pydantic 모델로 명시 (`response_model=`). dict 반환은 작은 액션에만.
- 요청 바디도 Pydantic 모델로 받는다. 본문 검증·문서화·OpenAPI 자동 생성에 필요.
- 모델 네이밍:
  - 도메인: `Block`, `Document`
  - 요청: `BlockCreate`, `BlockUpdate`
  - 응답: `BlockRead`, `DocumentRead`
- ORM 객체를 그대로 반환하지 말고, Pydantic 모델로 변환해서 노출 (정보 누출 방지 + 안정적 스키마).

## 에러 처리

- 클라이언트 잘못은 `HTTPException` 으로 상태 코드와 메시지 명시.
- 서버 내부 오류는 raise 하여 FastAPI 가 500 으로 변환하게 한다 (스택은 로그로).
- 메시지는 짧고 명확하게. 한국어/영어 어느 쪽이든 일관되게 사용.

```python
if block is None:
  raise HTTPException(status.HTTP_404_NOT_FOUND, "block not found")
if block.document_id != document_id:
  raise HTTPException(status.HTTP_400_BAD_REQUEST, "block does not belong to document")
```

## 비동기 vs 동기

- SQLite + SQLAlchemy(sync) 를 사용하므로 라우터는 **동기 함수**로 작성한다.
- 굳이 `async def` 로 만들지 않는다 (이벤트 루프 블로킹 + 이득 없음).
- 외부 HTTP 호출이 필요하면 그 함수만 `async def` + `httpx.AsyncClient` 로.

## 경로 / 쿼리 파라미터

- 경로 파라미터는 식별자만: `/api/documents/{document_id}`.
- 필터·페이지네이션은 쿼리스트링: `?limit=20&cursor=...`.
- URL 은 소문자, 단어 구분은 `-` 또는 `_` 중 하나로 고정 (현 코드베이스 컨벤션을 따른다).

## 인증 / 인가

- `app/auth/` 에 세션 의존성 정의.
- 보호된 라우터는 `Depends(get_current_user)` 형태로 의존성 추가.
- 권한 체크는 라우터 또는 service 레이어에서 명시적으로. repository 는 권한 무관.

## OpenAPI

- `summary`, `description`, `responses` 인자를 활용해 OpenAPI 가 의미 있게 생성되도록 한다.
- 비공개 내부 라우터는 `include_in_schema=False`.
