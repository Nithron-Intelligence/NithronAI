"""
nAI Core network helpers
Fetching user-supplied URLs without exposing the internal network (SSRF protection).
"""

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import aiohttp
from aiohttp.abc import AbstractResolver, ResolveResult
from aiohttp.resolver import DefaultResolver

REDIRECT_STATUSES = {301, 302, 303, 307, 308}


class UnsafeURLError(ValueError):
    """The URL is malformed or points at a non-public address."""


class FetchError(Exception):
    """The URL could not be fetched."""


class NonPublicAddressError(OSError):
    """Raised by PublicOnlyResolver when a host only resolves to non-public addresses."""


def is_public_ip(address: str) -> bool:
    """True only for globally routable unicast addresses."""
    try:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def _literal_ip(host: str) -> str | None:
    try:
        ipaddress.ip_address(host.strip("[]"))
        return host.strip("[]")
    except ValueError:
        return None


class PublicOnlyResolver(AbstractResolver):
    """
    DNS resolver that drops non-public addresses. Because every connection (including
    redirects) resolves through it, DNS-rebinding tricks can't reach internal hosts.
    """

    def __init__(self) -> None:
        self._resolver = DefaultResolver()

    async def resolve(
        self, host: str, port: int = 0, family: socket.AddressFamily = socket.AF_INET
    ) -> list[ResolveResult]:
        results = await self._resolver.resolve(host, port, family)
        public = [r for r in results if is_public_ip(r["host"])]
        if not public:
            raise NonPublicAddressError(f"{host} does not resolve to a public address")
        return public

    async def close(self) -> None:
        await self._resolver.close()


def validate_url(url: str, allow_private: bool = False) -> str:
    """Check scheme/host and reject literal private IPs. Returns the hostname."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeURLError("Only http and https URLs are supported")
    if not parsed.hostname:
        raise UnsafeURLError("Invalid URL")
    if parsed.username or parsed.password:
        raise UnsafeURLError("URLs with embedded credentials are not supported")
    literal = _literal_ip(parsed.hostname)
    if literal and not allow_private and not is_public_ip(literal):
        raise UnsafeURLError("URL points to a private or reserved address")
    return parsed.hostname


@dataclass
class FetchResult:
    content: bytes
    content_type: str
    final_url: str


async def fetch_url(
    url: str,
    *,
    max_bytes: int,
    timeout_seconds: float = 30,
    allow_private: bool = False,
    max_redirects: int = 5,
) -> FetchResult:
    """
    GET a URL with size, timeout and redirect limits. Unless ``allow_private`` is set,
    only public addresses are contacted (checked for literal IPs and at DNS resolution).
    """
    connector = aiohttp.TCPConnector(resolver=None if allow_private else PublicOnlyResolver())
    timeout = aiohttp.ClientTimeout(total=timeout_seconds)
    current = url

    try:
        async with aiohttp.ClientSession(connector=connector, timeout=timeout, trust_env=False) as session:
            for _ in range(max_redirects + 1):
                validate_url(current, allow_private)
                async with session.get(current, allow_redirects=False) as response:
                    if response.status in REDIRECT_STATUSES:
                        location = response.headers.get("Location")
                        if not location:
                            raise FetchError(f"Redirect without Location (HTTP {response.status})")
                        current = urljoin(current, location)
                        continue
                    if response.status != 200:
                        raise FetchError(f"Failed to fetch URL: HTTP {response.status}")

                    declared = response.content_length
                    if declared is not None and declared > max_bytes:
                        raise FetchError(f"Content too large ({declared} bytes)")

                    chunks: list[bytes] = []
                    size = 0
                    async for chunk in response.content.iter_chunked(65536):
                        size += len(chunk)
                        if size > max_bytes:
                            raise FetchError(f"Content too large (> {max_bytes} bytes)")
                        chunks.append(chunk)

                    return FetchResult(
                        content=b"".join(chunks),
                        content_type=response.headers.get("Content-Type", ""),
                        final_url=current,
                    )
            raise FetchError("Too many redirects")
    except aiohttp.ClientConnectorError as e:
        if isinstance(getattr(e, "os_error", None), NonPublicAddressError) or isinstance(
            e.__cause__, NonPublicAddressError
        ):
            raise UnsafeURLError("URL resolves to a private or reserved address") from e
        raise FetchError(f"Could not connect: {e}") from e
    except (aiohttp.ClientError, TimeoutError) as e:
        raise FetchError(f"Failed to fetch URL: {e}") from e
