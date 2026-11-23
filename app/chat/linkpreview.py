"""Link previews: the title and picture under a link in a message, like WhatsApp.

The server fetches the page (never the phones), so:
- a student's phone never contacts a site just because a link was sent;
- the picture is checked for nudity (same NudeNet check as photos) and the title against the word
  list before anyone sees them; a preview that fails is simply not shown;
- private/internal addresses are refused (nobody can make the server fetch its own network).

YouTube links use YouTube's own oEmbed (title, channel) and its thumbnail.
Results are kept 7 days in Mongo (link_previews). Firebase: chatConfig/messages/linkPreviews.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import html
import ipaddress
import logging
import re
import socket
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests

from . import moderation
from .mongo import db

log = logging.getLogger(__name__)

KEEP_DAYS = 7
PAGE_MAX = 400 * 1024          # read at most this much of a page (the <head> is at the top)
IMAGE_MAX = 3 * 1024 * 1024
TIMEOUT = 5
UA = "Mozilla/5.0 (compatible; ChatLinkPreview/1.0)"

_YT = re.compile(r"(?:youtube\.com/(?:watch\?(?:.*&)?v=|shorts/|live/|embed/)|youtu\.be/)([A-Za-z0-9_-]{11})", re.I)


def youtube_id(url: str) -> Optional[str]:
    m = _YT.search(url or "")
    return m.group(1) if m else None


def _public_host(host: str) -> bool:
    """True only for addresses on the public internet."""
    if not host:
        return False
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            return False
    return True


def _get(url: str, limit: int, accept: str) -> tuple[Optional[str], Optional[bytes], str]:
    """(final url, body up to [limit], content type). Follows up to 3 redirects, each checked."""
    for _ in range(4):
        u = urlparse(url)
        if u.scheme not in ("http", "https") or not _public_host(u.hostname or ""):
            return None, None, ""
        try:
            r = requests.get(url, headers={"User-Agent": UA, "Accept": accept}, timeout=TIMEOUT,
                             stream=True, allow_redirects=False)
        except requests.RequestException:
            return None, None, ""
        if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
            url = urljoin(url, r.headers["location"])
            r.close()
            continue
        if r.status_code != 200:
            r.close()
            return None, None, ""
        body, size = [], 0
        for chunk in r.iter_content(16 * 1024):
            body.append(chunk)
            size += len(chunk)
            if size >= limit:
                break
        r.close()
        return url, b"".join(body)[:limit], (r.headers.get("content-type") or "").lower()
    return None, None, ""


_META = re.compile(r"<meta\s+[^>]*>", re.I | re.S)
_ATTR = re.compile(r'([a-zA-Z:_-]+)\s*=\s*("([^"]*)"|\'([^\']*)\')', re.S)
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)


def parse_head(page: str) -> dict:
    """og:/twitter: tags, else the <title>."""
    tags: dict[str, str] = {}
    for m in _META.finditer(page):
        attrs = {a.group(1).lower(): (a.group(3) if a.group(3) is not None else a.group(4)) for a in _ATTR.finditer(m.group(0))}
        key = (attrs.get("property") or attrs.get("name") or "").lower()
        if key and attrs.get("content") and key not in tags:
            tags[key] = html.unescape(attrs["content"]).strip()
    title = tags.get("og:title") or tags.get("twitter:title")
    if not title:
        t = _TITLE.search(page)
        title = html.unescape(re.sub(r"\s+", " ", t.group(1))).strip() if t else ""
    return {
        "title": (title or "")[:200],
        "description": (tags.get("og:description") or tags.get("description") or tags.get("twitter:description") or "")[:300],
        "image": tags.get("og:image") or tags.get("og:image:url") or tags.get("twitter:image") or "",
        "site": (tags.get("og:site_name") or "")[:80],
    }


def _safe_image(url: str) -> bool:
    """The picture is fetched and checked for nudity before any phone shows it."""
    final, data, ctype = _get(url, IMAGE_MAX, "image/*")
    if not data:
        return False
    try:
        from . import media_scan
        res = media_scan.check_image(data)
    except Exception:  # noqa: BLE001
        log.exception("link preview: image check failed")
        return False
    return res.checked and res.allowed


def _clean_text(*parts: str) -> bool:
    text = " ".join(p for p in parts if p)
    return not text or moderation.check(text, is_staff=True, ai=False).allowed


def build(url: str) -> dict:
    """The preview for [url] (not cached). {} when there is nothing worth showing."""
    vid = youtube_id(url)
    if vid:
        info = {"title": "", "description": "", "site": "YouTube", "image": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"}
        try:
            r = requests.get("https://www.youtube.com/oembed", params={"url": f"https://www.youtube.com/watch?v={vid}",
                                                                      "format": "json"}, timeout=TIMEOUT)
            if r.status_code == 200:
                j = r.json()
                info["title"] = str(j.get("title") or "")[:200]
                info["description"] = str(j.get("author_name") or "")[:300]
        except Exception:  # noqa: BLE001
            pass
        if not _clean_text(info["title"], info["description"]):
            return {}
        if not _safe_image(info["image"]):
            info["image"] = ""
        return {**info, "video": True}
    final, body, ctype = _get(url, PAGE_MAX, "text/html")
    if not body or "html" not in ctype:
        return {}
    info = parse_head(body.decode("utf-8", errors="replace"))
    if not info["title"]:
        return {}
    if not _clean_text(info["title"], info["description"], info["site"]):
        return {}
    if info["image"]:
        img = urljoin(final or url, info["image"])
        if not img.startswith("https://") or not _safe_image(img):
            img = ""
        info["image"] = img
    return {**info, "video": False}


_asked: dict[str, list[float]] = {}


def allowed(user_id: str, per_minute: int = 30) -> bool:
    """Each person can have at most [per_minute] new pages fetched a minute (cached ones are free)."""
    import time
    now = time.time()
    recent = [t for t in _asked.get(user_id, []) if now - t < 60]
    if len(recent) >= per_minute:
        _asked[user_id] = recent
        return False
    recent.append(now)
    _asked[user_id] = recent
    if len(_asked) > 50_000:
        _asked.clear()
    return True


def cached(url: str) -> Optional[dict]:
    hit = db().link_previews.find_one({"_id": hashlib.sha1((url or "").strip().encode()).hexdigest()})
    if hit:
        hit.pop("_id", None)
        hit.pop("expiresAt", None)
    return hit


def preview(url: str) -> dict:
    """Cached for 7 days. Always a dict: {"url", "title", ...} or {"url"} alone (nothing to show)."""
    url = (url or "").strip()
    if not url.lower().startswith(("http://", "https://")) or len(url) > 1000:
        return {"url": url}
    key = hashlib.sha1(url.encode()).hexdigest()
    hit = db().link_previews.find_one({"_id": key})
    if hit:
        hit.pop("_id", None)
        hit.pop("expiresAt", None)
        return hit
    try:
        data = build(url)
    except Exception:  # noqa: BLE001
        log.exception("link preview failed for %s", url[:120])
        data = {}
    out = {"url": url, **data}
    db().link_previews.update_one({"_id": key}, {"$set": {
        **out, "expiresAt": dt.datetime.utcnow() + dt.timedelta(days=KEEP_DAYS)}}, upsert=True)
    return out
