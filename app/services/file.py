"""범용 파일 저장·조회·삭제 서비스.

허용 확장자 화이트리스트 검증과 UUID 기반 저장명으로
경로 순회(path traversal) 및 파일명 충돌을 방지합니다.

참고:
  - OWASP File Upload Cheat Sheet:
    https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html
  - RFC 5987 (Content-Disposition filename encoding):
    https://datatracker.ietf.org/doc/html/rfc5987
"""
from __future__ import annotations

import re
import unicodedata
import uuid
from pathlib import Path

# 파일 저장 디렉터리 — static/files/ (이미지 업로드 경로 static/uploads/ 와 분리)
FILES_DIR = Path(__file__).resolve().parents[2] / "static" / "files"

# 파일 크기 상한: 50 MB
MAX_BYTES = 50 * 1024 * 1024

# 허용 확장자 화이트리스트 — 실행 가능 파일(exe, sh, py, js 등) 제외
# Ref: OWASP File Upload Cheat Sheet
ALLOWED_EXTENSIONS: frozenset[str] = frozenset({
  # 문서
  ".pdf", ".doc", ".docx", ".odt",
  ".xls", ".xlsx", ".ods",
  ".ppt", ".pptx", ".odp",
  ".txt", ".md", ".csv",
  # 압축 아카이브
  ".zip", ".tar", ".gz", ".bz2", ".7z",
  # 이미지 (image 블록 외 첨부 용도)
  ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg",
  # 오디오/비디오
  ".mp3", ".m4a", ".wav", ".ogg",
  ".mp4", ".mov", ".avi", ".mkv", ".webm",
})

# 원본 파일명 최대 길이 (OS 제한 범위 내)
MAX_FILENAME_LENGTH = 255

# 경로 구분자·null byte·제어 문자 패턴 — sanitize 시 제거 대상
_UNSAFE_FILENAME_RE = re.compile(r'[/\\:*?"<>|\x00-\x1f]')


def sanitize_filename(name: str) -> str:
  """원본 파일명에서 경로 순회·제어 문자를 제거하고 최대 길이로 잘라 반환합니다.

  저장 경로에는 사용하지 않으며, DB 기록 및 Content-Disposition 헤더 전용입니다.

  Args:
    name: 클라이언트가 전송한 원본 파일명.

  Returns:
    NFC 정규화 및 위험 문자 제거 후 안전한 파일명 문자열.
  """
  # NFC 정규화 — 유니코드 합성 형식 통일 (한글 자모 분리 방지)
  name = unicodedata.normalize("NFC", name)
  # 경로 구분자 등 위험 문자를 밑줄로 치환
  name = _UNSAFE_FILENAME_RE.sub("_", name)
  name = name[:MAX_FILENAME_LENGTH]
  return name.strip() or "unnamed"


def validate_extension(filename: str) -> str:
  """파일명에서 확장자를 추출하고 허용 목록에 있는지 검증합니다.

  Args:
    filename: 원본 파일명 (확장자 포함).

  Returns:
    소문자 확장자 문자열 (예: ".pdf").

  Raises:
    ValueError: 확장자가 없거나 허용 목록에 없는 경우.
  """
  ext = Path(filename).suffix.lower()
  if not ext:
    raise ValueError("파일 확장자가 없습니다.")
  if ext not in ALLOWED_EXTENSIONS:
    raise ValueError(f"허용하지 않는 파일 형식입니다: {ext}")
  return ext


def save_file(data: bytes, original_filename: str) -> dict[str, str | int]:
  """파일을 UUID 기반 이름으로 디스크에 저장하고 메타데이터를 반환합니다.

  저장 경로에는 UUID만 사용하므로 파일명 충돌과 경로 순회 위험이 없습니다.
  원본 파일명은 sanitize_filename()을 통해 정규화됩니다.

  Args:
    data: 저장할 파일 바이트.
    original_filename: 클라이언트가 전송한 원본 파일명.

  Returns:
    stored_filename, size_bytes, sanitized_filename 을 담은 dict.

  Raises:
    ValueError: 파일 크기가 MAX_BYTES를 초과하는 경우.
  """
  # 서비스 레이어에서 크기 제한을 강제하여 라우터 외부 호출 경로에서도 안전성 보장
  # Ref: OWASP File Upload Cheat Sheet — "Limit the file size"
  if len(data) > MAX_BYTES:
    raise ValueError(f"파일 크기가 {MAX_BYTES // (1024 * 1024)} MB를 초과합니다.")

  FILES_DIR.mkdir(parents=True, exist_ok=True)

  stored_filename = uuid.uuid4().hex
  dest = FILES_DIR / stored_filename
  dest.write_bytes(data)

  return {
    "stored_filename": stored_filename,
    "size_bytes": len(data),
    "sanitized_filename": sanitize_filename(original_filename),
  }


def get_file_path(stored_filename: str) -> Path:
  """저장된 파일의 절대 경로를 반환합니다.

  경로 순회 공격 방어:
    stored_filename 해석 결과가 FILES_DIR 밖을 가리키면 ValueError를 발생시킵니다.
    (예: "../secret" 같은 입력 차단)

  Args:
    stored_filename: DB에 기록된 UUID 파일명.

  Returns:
    파일의 절대 Path 객체.

  Raises:
    ValueError: stored_filename이 FILES_DIR 밖을 가리키는 경우.
    FileNotFoundError: 파일이 존재하지 않는 경우.
  """
  path = (FILES_DIR / stored_filename).resolve()
  # resolve() 후 FILES_DIR.resolve() 하위인지 확인 — path traversal 방어
  if not path.is_relative_to(FILES_DIR.resolve()):
    raise ValueError("허용되지 않는 파일 경로입니다.")
  if not path.exists():
    raise FileNotFoundError(f"파일을 찾을 수 없습니다: {stored_filename}")
  return path


def delete_stored_file(stored_filename: str) -> bool:
  """디스크에서 파일을 삭제하고 성공 여부를 반환합니다.

  존재하지 않는 파일에 대해서는 False를 반환하며 예외를 던지지 않습니다.

  Args:
    stored_filename: DB에 기록된 UUID 파일명.

  Returns:
    삭제 성공 시 True, 파일이 없었거나 경로가 유효하지 않으면 False.
  """
  try:
    path = get_file_path(stored_filename)
    path.unlink()
    return True
  except (FileNotFoundError, ValueError):
    return False
