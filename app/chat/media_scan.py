"""
Checks photos and documents for nudity after they are delivered, on this server.

Free, no key and no daily limit: NudeNet (MIT licence, a 12 MB model run with onnxruntime)
looks at photos and at the first pages of a PDF; the text in a PDF goes through the same word
list as messages. A file that fails is taken down within a second or two (see service._take_down).

Memory: the model loads only when the first file arrives (~140 MB), with onnxruntime's
memory-saving settings, and files are checked one at a time. Voice notes are not checked.
"""
from __future__ import annotations

import gzip
import logging
import os
import threading
from dataclasses import dataclass, field
from typing import Optional

from . import chatconfig, media, moderation

log = logging.getLogger(__name__)

# What counts as nudity. Shirtless boys (MALE_BREAST_EXPOSED), bellies, feet and covered parts
# don't. Each class has its own bar: the more certain it has to be, the fewer false alarms.
UNSAFE = {
    "FEMALE_GENITALIA_EXPOSED": 0.40,
    "MALE_GENITALIA_EXPOSED": 0.40,
    "ANUS_EXPOSED": 0.40,
    "FEMALE_BREAST_EXPOSED": 0.50,
    "BUTTOCKS_EXPOSED": 0.55,
}
MAX_SIDE = 1280                 # photos are checked at most this big (the model works at 320 px)
MAX_DOWNLOAD = 25 * 1024 * 1024

_detector = None
_load_lock = threading.Lock()
_one_at_a_time = threading.Lock()


@dataclass
class ScanResult:
    allowed: bool = True
    reasons: list = field(default_factory=list)
    checked: bool = True        # False when it couldn't be checked (no storage, unreadable file…)


def _scan_config() -> dict:
    c = chatconfig.get()["media"].get("scan") or {}
    return {
        "images": bool(c.get("images", True)),
        "documents": bool(c.get("documents", True)),
        "documentPages": max(1, min(int(c.get("documentPages", 5) or 5), 20)),
        "strictness": float(c.get("strictness", 1.0) or 1.0),
    }


def _get_detector():
    """Loads the model the first time it is needed, with the settings that use the least memory."""
    global _detector
    if _detector is not None:
        return _detector
    with _load_lock:
        if _detector is None:
            import onnxruntime
            import nudenet
            from nudenet.nudenet import NudeDetector
            opts = onnxruntime.SessionOptions()
            opts.enable_cpu_mem_arena = False      # no big memory pool kept around between checks
            opts.enable_mem_pattern = False
            opts.intra_op_num_threads = 1          # the server has half a CPU: one thread is enough
            opts.inter_op_num_threads = 1
            path = os.path.join(os.path.dirname(nudenet.__file__), "320n.onnx")
            d = NudeDetector.__new__(NudeDetector)  # NudeDetector() would build a heavier session first
            d.onnx_session = onnxruntime.InferenceSession(path, sess_options=opts, providers=["CPUExecutionProvider"])
            d.input_width = d.input_height = 320
            d.input_name = d.onnx_session.get_inputs()[0].name
            _detector = d
            log.info("chat: nudity check model loaded")
    return _detector


def _off_the_event_loop(fn, *args):
    """The model is pure CPU work: on the live server it runs in a real thread, so nobody's
    messages wait while a photo is being checked."""
    try:
        from eventlet import patcher, tpool
        if patcher.is_monkey_patched("socket"):
            return tpool.execute(fn, *args)
    except ImportError:
        pass
    return fn(*args)


def _image_hits(bgr, strictness: float) -> list[str]:
    detections = _get_detector().detect(bgr) or []
    hits = []
    for d in detections:
        bar = UNSAFE.get(d.get("class"))
        if bar is not None and float(d.get("score") or 0) >= min(0.95, bar / max(strictness, 0.1)):
            hits.append(d["class"].lower())
    return sorted(set(hits))


def _decode(data: bytes):
    import cv2
    import numpy as np
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)   # always 3 colour channels
    if img is None:
        return None
    h, w = img.shape[:2]
    if max(h, w) > MAX_SIDE:
        f = MAX_SIDE / float(max(h, w))
        img = cv2.resize(img, (max(1, int(w * f)), max(1, int(h * f))), interpolation=cv2.INTER_AREA)
    return img


def check_image(data: bytes) -> ScanResult:
    cfg = _scan_config()
    img = _decode(data)
    if img is None:
        return ScanResult(checked=False)
    with _one_at_a_time:
        hits = _off_the_event_loop(_image_hits, img, cfg["strictness"])
    return ScanResult(allowed=not hits, reasons=[f"nudity:{h}" for h in hits])


def _pdf_pages(data: bytes, pages: int):
    """Text and pictures of the first [pages] pages (pypdfium2: Chrome's PDF engine, Apache/BSD)."""
    import numpy as np
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(data)
    try:
        texts, images = [], []
        for i in range(min(len(doc), pages)):
            page = doc[i]
            try:
                tp = page.get_textpage()
                texts.append(tp.get_text_range() or "")
                tp.close()
                w, h = page.get_size()
                scale = min(2.0, 1100.0 / max(w, h, 1.0))       # about 1100 px on the long side
                bitmap = page.render(scale=scale)
                arr = np.array(bitmap.to_pil().convert("RGB"))[:, :, ::-1].copy()   # RGB → BGR for the model
                bitmap.close()
                images.append(arr)
            finally:
                page.close()
        return "\n".join(texts), images
    finally:
        doc.close()


def check_pdf(data: bytes) -> ScanResult:
    cfg = _scan_config()
    try:
        with _one_at_a_time:
            text, images = _off_the_event_loop(_pdf_pages, data, cfg["documentPages"])
    except Exception:  # noqa: BLE001 - a broken or locked PDF
        log.info("chat: PDF could not be opened for checking")
        return ScanResult(checked=False)
    reasons = []
    if text.strip():
        words = moderation.check(text[:20000], is_staff=True, ai=False)    # vulgar words; links / numbers are fine in notes
        if not words.allowed:
            reasons += [f"pdf_text:{r}" for r in words.reasons]
    for img in images:
        with _one_at_a_time:
            hits = _off_the_event_loop(_image_hits, img, cfg["strictness"])
        if hits:
            reasons += [f"nudity:{h}" for h in hits]
            break
    return ScanResult(allowed=not reasons, reasons=sorted(set(reasons)))


def sniff(head: bytes) -> str:
    """What a file really is, from its first bytes: "pdf", "image" (one we can read), "image_other"
    (GIF / HEIC / AVIF / BMP…: an image the model can't take directly) or "other"."""
    h = head or b""
    if h[:5] == b"%PDF-":
        return "pdf"
    if h[:3] == b"\xff\xd8\xff" or h[:8] == b"\x89PNG\r\n\x1a\n" or (h[:4] == b"RIFF" and h[8:12] == b"WEBP"):
        return "image"
    if h[:6] in (b"GIF87a", b"GIF89a") or h[:2] == b"BM" or (h[4:8] == b"ftyp" and h[8:12] in (
            b"heic", b"heix", b"hevc", b"mif1", b"msf1", b"avif", b"avis")):
        return "image_other"
    return "other"


def _frames_via_pillow(data: bytes, frames: int = 3) -> list:
    """GIF (first frames), BMP and anything else Pillow opens, as pictures the model can take."""
    import io
    import numpy as np
    from PIL import Image, ImageSequence
    out = []
    try:
        with Image.open(io.BytesIO(data)) as im:
            for i, frame in enumerate(ImageSequence.Iterator(im)):
                if i >= frames:
                    break
                rgb = frame.convert("RGB")
                rgb.thumbnail((MAX_SIDE, MAX_SIDE))
                out.append(np.array(rgb)[:, :, ::-1].copy())
    except Exception:  # noqa: BLE001
        return []
    return out


def check_media(md: dict, strict: bool = False) -> ScanResult:
    """A delivered photo or document, checked by what the file really is (its first bytes), never
    by the type the app claimed: a photo sent as a "document" is still checked as a photo.
    Voice notes and other documents (Word, PowerPoint…) are let through.
    [strict] (students): a picture that can't be checked at all is treated as failing."""
    cfg = _scan_config()
    if md.get("kind") == "audio" or not media.enabled() or not md.get("key"):
        return ScanResult(checked=False)
    if md.get("gzip"):
        data = media.read(md["key"], MAX_DOWNLOAD)
        if data is None:
            return ScanResult(checked=False)
        try:
            data = gzip.decompress(data)
        except OSError:
            return ScanResult(checked=False)
        what = sniff(data[:32])
    else:
        data = None
        start = media.head(md["key"], 32)
        if start is None:                            # a ranged read failed: read the file itself
            data = media.read(md["key"], MAX_DOWNLOAD)
            start = data[:32] if data else b""
        what = sniff(start)
    if what == "other" or (what == "pdf" and not cfg["documents"]) or (what != "pdf" and not cfg["images"]):
        return ScanResult(checked=False)
    if data is None:
        data = media.read(md["key"], MAX_DOWNLOAD)
        if data is None:
            return ScanResult(allowed=not strict, reasons=[] if not strict else ["unchecked"], checked=False)
    if what == "pdf":
        return check_pdf(data)
    if what == "image":
        res = check_image(data)
        if res.checked:
            return res
    frames = _frames_via_pillow(data)
    if not frames:
        return ScanResult(allowed=not strict, reasons=[] if not strict else ["unchecked"], checked=False)
    for img in frames:
        with _one_at_a_time:
            hits = _off_the_event_loop(_image_hits, img, cfg["strictness"])
        if hits:
            return ScanResult(allowed=False, reasons=[f"nudity:{h}" for h in hits])
    return ScanResult()
