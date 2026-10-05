"""抽出済みレシピを Markdown / HTML に組み立てる。

手順には「根拠」として、その工程が写るフレームのサムネ画像と、秒数（タップで動画シーク）を付ける。
材料はテキストのみ（名前＋分量）。
"""

from __future__ import annotations

import base64
import html

from app.models import Frame, Recipe


def _mmss(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 60}:{s % 60:02d}"


def _nearest_frame(frames: list[Frame], seconds: float) -> Frame | None:
    if not frames:
        return None
    return min(frames, key=lambda f: abs(f.seconds - seconds))


def build_markdown(recipe: Recipe, url: str, uploader: str, video_id: str | None = None) -> str:
    """固定スキーマの Markdown に整形（手順には秒数リンク）。"""
    lines: list[str] = [f"# {recipe.title}", "", "## 材料"]

    if recipe.ingredients:
        for ing in recipe.ingredients:
            amount = ing.amount.strip() if ing.amount else ""
            lines.append(f"- {ing.name} {amount}".rstrip())
    else:
        lines.append("- （材料情報なし）")

    lines += ["", "## 手順"]
    if recipe.steps:
        for i, st in enumerate(recipe.steps, start=1):
            line = f"{i}. {st.text}"
            if video_id and st.seconds is not None:
                s = int(st.seconds)
                line += f"（▶{_mmss(st.seconds)}: https://youtu.be/{video_id}?t={s}s）"
            lines.append(line)
    else:
        lines.append("1. （手順情報なし）")

    source = f"出典: {url}"
    if uploader:
        source += f"（{uploader}）"
    lines += ["", "---", source]

    return "\n".join(lines)


def build_html(
    recipe: Recipe,
    url: str,
    uploader: str,
    video_id: str | None = None,
    frames: list[Frame] | None = None,
) -> str:
    """整形済みHTML。手順にサムネ＋秒数ボタン（動画シーク用 data-seconds）を付ける。"""
    frames = frames or []

    def esc(s: str) -> str:
        return html.escape(s or "")

    # プレイヤー本体はフロント側（index.html）に常駐。ここでは手順の ▶ ボタンだけ出す。
    parts: list[str] = [f"<h1>{esc(recipe.title)}</h1>"]

    parts.append("<h2>材料</h2><ul>")
    if recipe.ingredients:
        for ing in recipe.ingredients:
            amount = f" {esc(ing.amount)}" if ing.amount else ""
            parts.append(f"<li>{esc(ing.name)}{amount}</li>")
    else:
        parts.append("<li>（材料情報なし）</li>")
    parts.append("</ul>")

    parts.append("<h2>手順</h2><ol>")
    if recipe.steps:
        for st in recipe.steps:
            thumb = ""
            btn = ""
            if st.seconds is not None:
                fr = _nearest_frame(frames, st.seconds)
                if fr:
                    b64 = base64.b64encode(fr.data).decode("ascii")
                    thumb = f'<img class="thumb" src="data:image/jpeg;base64,{b64}" alt="">'
                if video_id:
                    btn = (
                        f'<button class="ts-btn" data-seconds="{int(st.seconds)}">'
                        f"▶ {_mmss(st.seconds)}</button>"
                    )
            parts.append(
                f'<li><div class="step">{thumb}'
                f'<div class="step-body">{esc(st.text)} {btn}</div></div></li>'
            )
    else:
        parts.append("<li>（手順情報なし）</li>")
    parts.append("</ol>")

    source = f'出典: <a href="{esc(url)}">{esc(url)}</a>'
    if uploader:
        source += f"（{esc(uploader)}）"
    parts += ["<hr>", f"<p>{source}</p>"]

    return "\n".join(parts)
