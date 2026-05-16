# 04. 테스트 (pytest)

## 도구

- `pytest`, `pytest-anyio`, `httpx` 로 라우터·로직 검증.
- 테스트는 `tests/` 디렉터리에. 파일명은 `test_<feature>.py`.

## 구조

`tests/conftest.py` 가 공통 픽스처 정의:

- `client`: `httpx.AsyncClient` 또는 FastAPI `TestClient`.
- `repo`: in-memory / 임시 SQLite repository.
- `dependency_overrides`: `app.dependency_overrides` 로 `get_repository` 를 테스트용으로 교체.

## 작성 규칙

- **Arrange / Act / Assert** 세 단계 구분.
- 테스트 함수명은 의도 + 기대 결과: `test_create_block_persists_payload`, `test_update_missing_block_returns_404`.
- 같은 시나리오의 변형은 `@pytest.mark.parametrize` 로.
- 외부 자원 (네트워크 / 파일) 은 mock — 단, SQLite 는 실제 사용 (가벼움).

```python
def test_create_text_block_returns_201(client, repo):
  resp = client.post(
    "/api/documents/doc-1/blocks",
    json={"type": "text", "content": {"text": "hello"}},
  )

  assert resp.status_code == 201
  body = resp.json()
  assert body["type"] == "text"
  assert repo.find_block(body["id"]) is not None
```

## 커버리지 / 임계값

- 새 라우터·repository 메서드는 최소 1개 happy path + 주요 에러 케이스 테스트.
- 전체 커버리지 임계값은 별도 강제하지 않지만, CI 의 `Test` 잡이 통과해야 머지.
- 회귀 테스트: 버그 수정 PR 은 그 버그를 재현하는 테스트가 함께 들어가야 한다.

## 빠른 명령

```bash
uv run pytest                       # 전체
uv run pytest tests/test_blocks.py  # 한 파일
uv run pytest -k "create"           # 이름 필터
uv run pytest -x --lf               # 마지막 실패만 / 첫 실패에서 멈춤
```

## 안티패턴

- 라우터를 우회해 repository 만 단독 테스트 → API 표면 회귀를 놓친다. 라우터 레벨 테스트가 우선.
- 시간 / 랜덤 의존 → 테스트가 flaky 해진다. `freezegun` 또는 의존성 주입으로 격리.
- 모든 케이스를 단일 거대 테스트에 — 실패 위치 파악이 어렵다. 시나리오 단위로 분할.
