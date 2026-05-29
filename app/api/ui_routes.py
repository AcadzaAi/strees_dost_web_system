from __future__ import annotations

from flask import Blueprint, current_app, send_from_directory

bp = Blueprint("ui", __name__)


@bp.get("/")
def index():
    return send_from_directory(current_app.static_folder, "index.html")


@bp.get("/login")
def login():
    return send_from_directory(current_app.static_folder, "login.html")


@bp.get("/proxy-image")
def proxy_image():
    """Proxy external images to avoid CORS/hotlinking blocks. Caches bytes in memory."""
    import requests as req
    from flask import request, Response
    from urllib.parse import urlparse, unquote
    
    url = request.args.get("url", "").strip()
    if not url:
        return Response("Missing url", status=400)
    
    # Fully decode — handle single, double, and triple encoding
    prev = None
    while prev != url:
        prev = url
        url = unquote(url)
    
    if not url.startswith("https://"):
        return Response("Invalid URL", status=400)
    
    try:
        domain = urlparse(url).netloc.lower()
    except Exception:
        return Response("Invalid URL", status=400)
    
    allowed = ["upload.wikimedia.org", "commons.wikimedia.org", "en.wikipedia.org"]
    if not any(domain == d or domain.endswith("." + d) for d in allowed):
        current_app.logger.warning("proxy-image blocked domain: %s", domain)
        return Response("Domain not allowed", status=403)
    
    # In-memory cache to avoid hitting Wikimedia repeatedly
    if not hasattr(proxy_image, "_cache"):
        proxy_image._cache = {}
    
    if url in proxy_image._cache:
        data, content_type = proxy_image._cache[url]
        return Response(data, status=200, content_type=content_type,
                       headers={"Cache-Control": "public, max-age=86400"})
    
    try:
        resp = req.get(
            url,
            timeout=8,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; FocusDost/1.0)",
                "Referer": "https://en.wikipedia.org/",
                "Accept": "image/*,*/*",
            },
        )
        if resp.status_code == 200:
            content_type = resp.headers.get("Content-Type", "image/jpeg")
            proxy_image._cache[url] = (resp.content, content_type)
            return Response(resp.content, status=200, content_type=content_type,
                           headers={"Cache-Control": "public, max-age=86400"})
        current_app.logger.warning("proxy-image upstream %d for %s", resp.status_code, url[:80])
        return Response("Upstream error", status=resp.status_code)
    except Exception as exc:
        current_app.logger.warning("proxy-image failed for %s: %s", url[:80], exc)
        return Response("Fetch failed", status=502)
