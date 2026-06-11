"""Tests del guard SSRF de web_read (PLAN_FINAL §9.1.3).

Solo se prueba `_validate_url` (puro, sin red): usa IPs literales para que
`getaddrinfo` resuelva localmente sin DNS externo.
"""

import pytest

from ssrf_guard import BlockedURL, _validate_url

PRIVATE_OR_LOCAL = [
    "http://127.0.0.1",
    "http://10.0.0.1",
    "http://192.168.1.10",
    "http://172.16.0.1",
    "http://169.254.169.254/latest/meta-data",  # cloud metadata (Hetzner/AWS)
    "http://[::1]",                              # IPv6 loopback
    "http://0.0.0.0",
]

BAD_SCHEME = [
    "ftp://example.com",
    "file:///etc/passwd",
    "gopher://x/_",
    "data:text/plain,hola",
]

PUBLIC = ["http://8.8.8.8", "https://1.1.1.1"]


@pytest.mark.parametrize("url", PRIVATE_OR_LOCAL)
def test_private_and_local_blocked(url):
    with pytest.raises(BlockedURL):
        _validate_url(url)


@pytest.mark.parametrize("url", BAD_SCHEME)
def test_non_http_schemes_blocked(url):
    with pytest.raises(BlockedURL):
        _validate_url(url)


def test_missing_hostname_blocked():
    with pytest.raises(BlockedURL):
        _validate_url("http://")


@pytest.mark.parametrize("url", PUBLIC)
def test_public_ip_allowed(url):
    assert _validate_url(url) == url
