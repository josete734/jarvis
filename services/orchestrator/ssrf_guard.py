"""SSRF guard for web_read (PLAN_FINAL §9.1.3, per OWASP SSRF cheat sheet).

Deny-by-default fetch: rejects private, loopback, link-local and reserved ranges
(incl. 169.254.169.254 metadata). The IP validation happens inside the aiohttp
resolver (`_ValidatingResolver`), i.e. at the SAME point aiohttp resolves to
connect — this closes the DNS-rebinding / TOCTOU window (a domain can't return a
public IP at validation and a private one at connection). `_validate_url` is a
cheap pre-check (scheme + literal-IP) kept for fast rejection and unit tests.
"""

import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import aiohttp
from aiohttp.resolver import ThreadedResolver

MAX_BYTES = 4 * 1024 * 1024          # 4 MB download cap
MAX_REDIRECTS = 3
TIMEOUT_SECS = 15
ALLOWED_SCHEMES = {"http", "https"}
ALLOWED_CONTENT = ("text/html", "text/plain", "application/xhtml", "application/xml")


class BlockedURL(Exception):
    pass


def _ip_blocked(ip_str: str) -> bool:
    ip = ipaddress.ip_address(ip_str)
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def _validate_host(host: str) -> None:
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise BlockedURL(f"DNS resolution failed for {host}: {e}") from e
    if not infos:
        raise BlockedURL(f"No addresses for {host}")
    for info in infos:
        if _ip_blocked(info[4][0]):
            raise BlockedURL(f"{host} resolves to disallowed address {info[4][0]}")


def _validate_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise BlockedURL(f"Scheme not allowed: {parsed.scheme!r}")
    if not parsed.hostname:
        raise BlockedURL("URL without hostname")
    _validate_host(parsed.hostname)
    return url


class _ValidatingResolver(ThreadedResolver):
    """aiohttp resolver that rejects non-public IPs at connection-resolution time.

    Validating here (instead of only in _validate_url) removes the TOCTOU gap:
    aiohttp connects to exactly the addresses this resolver returns.
    """

    async def resolve(self, host, port=0, family=socket.AF_INET):
        hosts = await super().resolve(host, port, family)
        for h in hosts:
            if _ip_blocked(h["host"]):
                raise BlockedURL(f"{host} resolved to disallowed address {h['host']}")
        return hosts


async def fetch_safe(url: str) -> str:
    """Fetch HTML/text with SSRF protections. Returns the raw body (str)."""
    timeout = aiohttp.ClientTimeout(total=TIMEOUT_SECS)
    headers = {"User-Agent": "Mozilla/5.0 (compatible; Jarvis-home/1.0)"}
    connector = aiohttp.TCPConnector(resolver=_ValidatingResolver())

    async with aiohttp.ClientSession(
        timeout=timeout, headers=headers, connector=connector
    ) as session:
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            _validate_url(current)                     # cheap pre-check (scheme + literal IP)
            async with session.get(current, allow_redirects=False) as resp:
                if resp.status in (301, 302, 303, 307, 308):
                    location = resp.headers.get("Location")
                    if not location:
                        raise BlockedURL("Redirect without Location header")
                    current = urljoin(current, location)
                    continue
                resp.raise_for_status()
                ctype = resp.headers.get("Content-Type", "").lower()
                if not any(ctype.startswith(a) for a in ALLOWED_CONTENT):
                    raise BlockedURL(f"Content-Type not allowed: {ctype!r}")
                chunks, size = [], 0
                async for chunk in resp.content.iter_chunked(65536):
                    size += len(chunk)
                    if size > MAX_BYTES:
                        break
                    chunks.append(chunk)
                charset = resp.charset or "utf-8"
                return b"".join(chunks).decode(charset, errors="replace")
        raise BlockedURL(f"Too many redirects (> {MAX_REDIRECTS})")
