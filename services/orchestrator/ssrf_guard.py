"""SSRF guard for web_read (PLAN_FINAL §9.1.3, per OWASP SSRF cheat sheet).

Deny-by-default fetch: resolves ALL A/AAAA records and rejects private,
loopback, link-local and reserved ranges (incl. 169.254.169.254 metadata)
BEFORE connecting; redirects are followed manually re-validating each hop.

Known residual: small DNS TOCTOU window between validation and connection
(documented; v3 of the plan adds an egress-deny network layer on top).
"""

import asyncio
import ipaddress
import socket
from urllib.parse import urlparse, urljoin

import aiohttp

MAX_BYTES = 4 * 1024 * 1024          # 4 MB download cap
MAX_REDIRECTS = 3
TIMEOUT_SECS = 15
ALLOWED_SCHEMES = {"http", "https"}
ALLOWED_CONTENT = ("text/html", "text/plain", "application/xhtml", "application/xml")


class BlockedURL(Exception):
    pass


def _validate_host(host: str) -> None:
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise BlockedURL(f"DNS resolution failed for {host}: {e}") from e
    if not infos:
        raise BlockedURL(f"No addresses for {host}")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise BlockedURL(f"{host} resolves to disallowed address {ip}")


def _validate_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise BlockedURL(f"Scheme not allowed: {parsed.scheme!r}")
    if not parsed.hostname:
        raise BlockedURL("URL without hostname")
    _validate_host(parsed.hostname)
    return url


async def fetch_safe(url: str) -> str:
    """Fetch HTML/text with SSRF protections. Returns the raw body (str)."""
    timeout = aiohttp.ClientTimeout(total=TIMEOUT_SECS)
    headers = {"User-Agent": "Mozilla/5.0 (compatible; Jarvis-home/1.0)"}

    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            await asyncio.to_thread(_validate_url, current)
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
