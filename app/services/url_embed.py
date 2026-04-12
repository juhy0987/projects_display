"""URL embed metadata fetching service.

책임:
  1. SSRF 방지 — 사설 네트워크·루프백 주소 차단
  2. Open Graph / Twitter Card / 기본 HTML 태그 우선순위 적용
  3. 로고 URL 결정 — og:image > apple-touch-icon > favicon 순
  4. 타임아웃·HTTP 에러 시 graceful fallback (status="error") 반환

참고 자료:
  - Open Graph Protocol: https://ogp.me/
  - Twitter Cards: https://developer.twitter.com/en/docs/twitter-for-websites/cards
  - OWASP SSRF Prevention Cheat Sheet:
    https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html
"""
from __future__ import annotations

import ipaddress
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Literal

# 요청 타임아웃 (초) — 느린 서버로 인한 UX 지연 방지
_FETCH_TIMEOUT: int = 10

# 파싱할 최대 응답 바이트 (2 MB) — 메모리 고갈 방지
_MAX_BODY_BYTES: int = 2 * 1024 * 1024

# 사설·예약 IP 대역 — SSRF 공격 방어를 위해 모두 차단
# Ref: RFC 1918, RFC 4193, RFC 3927, RFC 6598
_BLOCKED_NETWORKS: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = [
  ipaddress.ip_network("10.0.0.0/8"),        # 사설 클래스 A
  ipaddress.ip_network("172.16.0.0/12"),      # 사설 클래스 B
  ipaddress.ip_network("192.168.0.0/16"),     # 사설 클래스 C
  ipaddress.ip_network("127.0.0.0/8"),        # IPv4 루프백
  ipaddress.ip_network("169.254.0.0/16"),     # 링크-로컬 (APIPA)
  ipaddress.ip_network("100.64.0.0/10"),      # 공유 주소 공간 (RFC 6598)
  ipaddress.ip_network("0.0.0.0/8"),          # "이 네트워크" (RFC 1122)
  ipaddress.ip_network("::1/128"),            # IPv6 루프백
  ipaddress.ip_network("fc00::/7"),           # IPv6 고유 로컬
  ipaddress.ip_network("fe80::/10"),          # IPv6 링크-로컬
]

# 요청 User-Agent — 대부분의 사이트에서 봇 차단을 피하기 위한 최소 식별자
_USER_AGENT = "Mozilla/5.0 (compatible; ProjectsDisplay/1.0; +metadata-fetch)"


@dataclass
class UrlEmbedMetadata:
  """fetch_url_metadata() 반환값 DTO."""

  url: str
  title: str = ""
  description: str = ""
  logo: str = ""        # 절대 URL (og:image / apple-touch-icon / favicon)
  provider: str = ""    # "www." 제거한 호스트명
  fetched_at: str = ""  # ISO-8601 UTC 타임스탬프
  status: Literal["success", "error"] = "success"
  error: str = ""       # status="error"일 때 사람이 읽을 수 있는 설명


# ── SSRF 방어 ─────────────────────────────────────────────────────────────────

def _is_ssrf_safe(url: str) -> bool:
  """URL이 공개 서버를 가리킬 때만 True를 반환한다.

  검사 항목:
    1. 프로토콜 — http 또는 https만 허용
    2. 호스트명 — 반드시 존재해야 함
    3. IP 해석 결과 — _BLOCKED_NETWORKS에 포함되면 차단

  Ref: OWASP SSRF Prevention Cheat Sheet
  """
  parsed = urllib.parse.urlparse(url)
  if parsed.scheme not in ("http", "https"):
    return False
  hostname = parsed.hostname
  if not hostname:
    return False

  try:
    # getaddrinfo는 단일 호스트명에 대해 여러 주소를 반환할 수 있으므로
    # 하나라도 사설 대역이면 차단 (SSRF DNS rebinding 방지)
    addr_infos = socket.getaddrinfo(hostname, None)
  except (socket.gaierror, OSError):
    # 도메인 해석 실패 → 안전하지 않음으로 처리
    return False

  for addr_info in addr_infos:
    raw_addr = addr_info[4][0]
    try:
      ip = ipaddress.ip_address(raw_addr)
    except ValueError:
      return False
    for net in _BLOCKED_NETWORKS:
      if ip in net:
        return False

  return True


# ── HTML 메타데이터 파서 ───────────────────────────────────────────────────────

class _MetaParser(HTMLParser):
  """Open Graph, Twitter Card, 기본 HTML 태그에서 메타데이터를 추출한다.

  <head> 종료 태그를 만나면 파싱을 중단해 불필요한 본문 처리 비용을 줄인다.
  """

  def __init__(self) -> None:
    super().__init__()
    self._og: dict[str, str] = {}
    self._twitter: dict[str, str] = {}
    self._meta_description: str = ""
    self._page_title: str = ""
    self._favicon: str = ""
    self._apple_icon: str = ""
    self._in_title: bool = False
    self._in_head: bool = True   # </head> 이후 파싱 생략
    self._title_buf: list[str] = []

  # HTMLParser 콜백 ─────────────────────────────────────────────────────────

  def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
    if not self._in_head:
      return
    attr = {k: (v or "") for k, v in attrs}

    if tag == "meta":
      self._handle_meta(attr)
    elif tag == "link":
      self._handle_link(attr)
    elif tag == "title":
      self._in_title = True
      self._title_buf = []

  def handle_data(self, data: str) -> None:
    if self._in_title:
      self._title_buf.append(data)

  def handle_endtag(self, tag: str) -> None:
    if tag == "title" and self._in_title:
      self._page_title = "".join(self._title_buf).strip()
      self._in_title = False
    elif tag == "head":
      self._in_head = False

  # 태그별 처리 ─────────────────────────────────────────────────────────────

  def _handle_meta(self, attr: dict[str, str]) -> None:
    prop = attr.get("property", "").lower()
    name = attr.get("name", "").lower()
    content = attr.get("content", "").strip()
    if not content:
      return

    # Open Graph — https://ogp.me/
    if prop.startswith("og:"):
      key = prop[3:]  # "og:" 제거
      if key in ("title", "description", "image"):
        self._og[key] = content

    # Twitter Card — https://developer.twitter.com/en/docs/twitter-for-websites/cards
    elif name.startswith("twitter:"):
      key = name[8:]  # "twitter:" 제거
      if key in ("title", "description", "image"):
        self._twitter[key] = content

    # 기본 meta description
    elif name == "description":
      self._meta_description = content

  def _handle_link(self, attr: dict[str, str]) -> None:
    rel = attr.get("rel", "").lower()
    href = attr.get("href", "").strip()
    if not href:
      return
    if "apple-touch-icon" in rel:
      self._apple_icon = href
    elif "icon" in rel:
      # "shortcut icon", "icon" 모두 포함
      self._favicon = href

  # 우선순위 적용된 결과값 ──────────────────────────────────────────────────

  @property
  def best_title(self) -> str:
    """og:title > twitter:title > <title> 순으로 반환."""
    return self._og.get("title") or self._twitter.get("title") or self._page_title

  @property
  def best_description(self) -> str:
    """og:description > twitter:description > meta[name=description] 순으로 반환."""
    return (
      self._og.get("description")
      or self._twitter.get("description")
      or self._meta_description
    )

  @property
  def best_logo(self) -> str:
    """og:image > apple-touch-icon > favicon 순으로 반환."""
    return self._og.get("image") or self._apple_icon or self._favicon


# ── 유틸리티 ──────────────────────────────────────────────────────────────────

def _resolve_url(base: str, url: str) -> str:
  """상대 URL을 절대 URL로 변환한다. 이미 절대 URL이면 그대로 반환."""
  if not url:
    return ""
  return urllib.parse.urljoin(base, url)


def _extract_provider(url: str) -> str:
  """URL에서 사람이 읽기 쉬운 제공자명(호스트명)을 추출한다.

  'www.' 접두어는 제거한다. (예: "www.example.com" → "example.com")
  """
  parsed = urllib.parse.urlparse(url)
  hostname = parsed.hostname or ""
  if hostname.startswith("www."):
    hostname = hostname[4:]
  return hostname


# ── SSRF-안전 리다이렉트 핸들러 ───────────────────────────────────────────────

class _SSRFRedirectHandler(urllib.request.HTTPRedirectHandler):
  """리다이렉트 목적지 URL을 추적할 때마다 SSRF 검사를 재실행한다.

  urllib의 기본 HTTPRedirectHandler는 Location 헤더를 아무 검사 없이 따라간다.
  서버가 초기 SSRF 검사를 통과한 뒤 내부 주소로 리다이렉트를 유도하는
  "open redirect via 30x" 공격을 방지하기 위해 각 목적지를 재검증한다.

  Ref: OWASP SSRF Prevention Cheat Sheet — Redirect Handling
       https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html
  """

  def redirect_request(
    self,
    req: urllib.request.Request,
    fp: object,
    code: int,
    msg: str,
    headers: object,
    newurl: str,
  ) -> urllib.request.Request | None:
    if not _is_ssrf_safe(newurl):
      raise urllib.error.URLError(f"리다이렉트 목적지가 허용되지 않는 주소입니다: {newurl}")
    return super().redirect_request(req, fp, code, msg, headers, newurl)


# ── 공개 API ─────────────────────────────────────────────────────────────────

def fetch_url_metadata(url: str) -> UrlEmbedMetadata:
  """지정 URL의 Open Graph / Twitter Card / HTML 메타데이터를 수집해 반환한다.

  우선순위 (높음 → 낮음):
    - title:       og:title > twitter:title > <title>
    - description: og:description > twitter:description > meta[name=description]
    - logo:        og:image > apple-touch-icon > favicon

  실패 시에도 예외를 던지지 않고 status="error"인 UrlEmbedMetadata를 반환한다.

  보안:
    - http / https 이외의 프로토콜 차단
    - 사설·루프백 IP 대역 차단 (SSRF 방지)
    - 응답 바디 최대 2 MB까지만 읽음 (메모리 보호)

  Args:
    url: 메타데이터를 조회할 HTTP(S) URL.

  Returns:
    UrlEmbedMetadata 인스턴스.
  """
  fetched_at = datetime.now(timezone.utc).isoformat()
  provider = _extract_provider(url)

  # ── 1. SSRF 사전 차단 ────────────────────────────────────────────────────
  if not _is_ssrf_safe(url):
    return UrlEmbedMetadata(
      url=url,
      provider=provider,
      fetched_at=fetched_at,
      status="error",
      error="허용되지 않는 URL입니다 (프로토콜 또는 대상 주소 제한).",
    )

  # ── 2. HTTP 요청 ──────────────────────────────────────────────────────────
  req = urllib.request.Request(
    url,
    headers={
      "User-Agent": _USER_AGENT,
      "Accept": "text/html,application/xhtml+xml,*/*;q=0.9",
      "Accept-Language": "ko,en;q=0.9",
    },
  )

  opener = urllib.request.build_opener(_SSRFRedirectHandler())
  try:
    with opener.open(req, timeout=_FETCH_TIMEOUT) as resp:
      content_type: str = resp.headers.get("Content-Type", "")
      # HTML이 아닌 응답(PDF, 이미지 등)은 파싱 대상이 아님
      if "html" not in content_type.lower():
        return UrlEmbedMetadata(
          url=url,
          provider=provider,
          fetched_at=fetched_at,
          status="error",
          error=f"HTML 응답이 아닙니다 (Content-Type: {content_type}).",
        )
      raw_body = resp.read(_MAX_BODY_BYTES)
      # Content-Type 헤더의 charset 파라미터를 우선 사용한다.
      # 예) "text/html; charset=euc-kr" → "euc-kr"
      # Ref: https://docs.python.org/3/library/http.client.html#http.client.HTTPResponse.headers
      try:
        charset = resp.headers.get_content_charset("utf-8") or "utf-8"
      except LookupError:
        charset = "utf-8"
      body = raw_body.decode(charset, errors="replace")

  except urllib.error.HTTPError as exc:
    return UrlEmbedMetadata(
      url=url,
      provider=provider,
      fetched_at=fetched_at,
      status="error",
      error=f"HTTP {exc.code}: {exc.reason}",
    )
  except urllib.error.URLError as exc:
    return UrlEmbedMetadata(
      url=url,
      provider=provider,
      fetched_at=fetched_at,
      status="error",
      error=f"URL 요청 실패: {exc.reason}",
    )
  except TimeoutError:
    return UrlEmbedMetadata(
      url=url,
      provider=provider,
      fetched_at=fetched_at,
      status="error",
      error="요청 시간이 초과되었습니다.",
    )

  # ── 3. HTML 파싱 ─────────────────────────────────────────────────────────
  parser = _MetaParser()
  try:
    parser.feed(body)
  except Exception:
    # 비정형 HTML에서 HTMLParser가 예외를 던질 수 있음 — 부분 추출 결과 사용
    pass

  logo = _resolve_url(url, parser.best_logo)

  return UrlEmbedMetadata(
    url=url,
    title=parser.best_title[:200],        # 비정상적으로 긴 title 방어
    description=parser.best_description[:500],
    logo=logo,
    provider=provider,
    fetched_at=fetched_at,
    status="success",
  )
