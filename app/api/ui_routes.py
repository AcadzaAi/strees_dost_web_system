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
    """Serve a downloaded, vision-verified image by its internal id.

    Images are produced by the OpenAI web-search pipeline in trigger_routes,
    which downloads + validates them and stores the raw bytes in memory. We
    serve those bytes directly so the browser never hotlinks an external host
    (which previously caused 400/403/429 errors).
    """
    from flask import request, Response

    img_id = request.args.get("id", "").strip()
    if not img_id:
        return Response("Missing id", status=400)

    try:
        from .trigger_routes import _retrieve_image
    except Exception as exc:  # pragma: no cover
        current_app.logger.error("proxy-image: cannot access image retrieval: %s", exc)
        return Response("Unavailable", status=503)

    entry = _retrieve_image(img_id)
    if not entry:
        current_app.logger.warning("proxy-image: unknown id %s", img_id)
        return Response("Not found", status=404)

    data, content_type = entry
    return Response(
        data,
        status=200,
        content_type=content_type or "image/jpeg",
        headers={"Cache-Control": "public, max-age=86400"},
    )
