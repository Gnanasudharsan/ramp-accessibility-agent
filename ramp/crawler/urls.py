"""URL normalisation and scope rules for the crawler."""

from __future__ import annotations

from urllib.parse import urldefrag, urljoin, urlsplit

SKIP_EXTENSIONS = frozenset(
    {
        ".pdf",
        ".zip",
        ".gz",
        ".tar",
        ".dmg",
        ".exe",
        ".msi",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".ppt",
        ".pptx",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".svg",
        ".webp",
        ".ico",
        ".mp3",
        ".mp4",
        ".mov",
        ".avi",
        ".webm",
        ".css",
        ".js",
        ".json",
        ".xml",
        ".rss",
        ".woff",
        ".woff2",
    }
)


def origin_of(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def normalize(url: str, base: str | None = None) -> str | None:
    """Absolute http(s) URL without fragment, or None if the link is out of scope by form."""
    joined = urljoin(base, url) if base else url
    joined, _ = urldefrag(joined)
    parts = urlsplit(joined)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None
    path = parts.path or "/"
    lowered = path.lower()
    if any(lowered.endswith(ext) for ext in SKIP_EXTENSIONS):
        return None
    query = f"?{parts.query}" if parts.query else ""
    return f"{parts.scheme}://{parts.netloc.lower()}{path}{query}"


def same_origin(a: str, b: str) -> bool:
    return origin_of(a).lower() == origin_of(b).lower()
