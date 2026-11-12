"""Network policy for the audit browser: no requests to private or internal addresses.

A public page must not be able to make Ramp's browser fetch ``http://169.254.169.254`` (cloud
metadata), ``http://redis:6379``, or anything on the host's private network (SSRF). Requests to
private, loopback, link-local, multicast, reserved, or unresolvable hosts are refused unless the
audit itself targets such a host (local development), which ``allow_private`` expresses.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit

_cache: dict[str, bool] = {}


def is_private_ip(value: str) -> bool:
    ip = ipaddress.ip_address(value)
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


async def host_is_private(host: str) -> bool:
    """True if ``host`` is, or resolves to, any non-public address (fails closed)."""
    host = host.strip("[]").lower()
    if host in _cache:
        return _cache[host]
    try:
        result = is_private_ip(host)
    except ValueError:
        if host == "localhost" or host.endswith((".localhost", ".internal", ".local")):
            result = True
        else:
            try:
                infos = await asyncio.get_running_loop().getaddrinfo(host, None)
                result = any(is_private_ip(str(info[4][0])) for info in infos) or not infos
            except (socket.gaierror, OSError):
                result = True
    _cache[host] = result
    return result


async def url_is_private(url: str) -> bool:
    host = urlsplit(url).hostname
    return True if host is None else await host_is_private(host)
