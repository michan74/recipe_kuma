"""YouTube URL から動画IDを抽出する。

shorts / watch / youtu.be / embed の表記揺れを同一IDに正規化し、
キャッシュのキーを安定させる。
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse


def extract_video_id(url: str) -> str | None:
    try:
        u = urlparse(url)
    except Exception:  # noqa: BLE001
        return None

    host = (u.hostname or "").lower()

    # youtu.be/XXXX
    if host.endswith("youtu.be"):
        vid = u.path.lstrip("/").split("/")[0]
        return vid or None

    if "youtube.com" in host:
        # /watch?v=XXXX
        if u.path == "/watch":
            v = parse_qs(u.query).get("v")
            return v[0] if v else None
        # /shorts/XXXX, /embed/XXXX, /v/XXXX
        parts = [p for p in u.path.split("/") if p]
        if len(parts) >= 2 and parts[0] in ("shorts", "embed", "v"):
            return parts[1]

    return None
