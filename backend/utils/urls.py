import ipaddress
import socket
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

TRACKING = {"fbclid", "gclid", "mc_cid", "mc_eid", "ref", "source"}


def normalize_url(url: str) -> str:
    p = urlparse(url.strip())
    query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not k.lower().startswith("utm_") and k.lower() not in TRACKING]
    return urlunparse((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/") or "/", "", urlencode(query), ""))


def is_safe_public_url(url: str) -> bool:
    try:
        p = urlparse(url)
        if p.scheme not in {"http", "https"} or not p.hostname or p.username or p.password: return False
        if p.hostname.lower() in {"localhost", "metadata.google.internal"}: return False
        for info in socket.getaddrinfo(p.hostname, None):
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast: return False
        return True
    except (ValueError, OSError, socket.gaierror): return False
