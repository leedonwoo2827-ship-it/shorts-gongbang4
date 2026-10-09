"""glossary — 용어·원문·도식을 한 장짜리 오프라인 HTML 로 (termbook-studio 의 「HTML 다운로드」를 단순하게).

jobs/<job>/glossary.html
  장마다 용어 목록 → 용어마다: 원고 소주제(원문 그대로·원고 SVG 포함) + 쇼츠용 개념 도식(있으면) + 영상 링크(올렸으면)
외부 폰트·CDN·스크립트 없음. 원고 마크업은 html_manuscript.sanitize 를 거친 것만 쓴다.
"""
from __future__ import annotations

import html
from typing import Any, Dict, List

from . import config
from .job import Job
from .log import log

CSS = """body{margin:0;font-family:'Malgun Gothic','Apple SD Gothic Neo',system-ui,sans-serif;color:#243649;background:#fff;line-height:1.8}
.wrap{max-width:980px;margin:0 auto;padding:32px 20px}h1{font-size:28px;margin:0 0 6px;color:#173e60}
.meta{color:#75879a;font-size:13px;margin-bottom:24px}nav{columns:2;font-size:13px;border:1px solid #e5eaf0;border-radius:8px;padding:14px 20px;margin-bottom:28px}
nav a{color:#1f4e79;text-decoration:none}h2{font-size:20px;border-bottom:2px solid #1f4e79;padding-bottom:6px;margin-top:44px;color:#1f4e79}
.term{border-top:1px solid #e5eaf0;padding:18px 0}.term h3{font-size:19px;margin:0 0 8px;color:#173e60}.sid{font-size:11px;color:#8b9bac;margin-left:8px;font-weight:400}
.src{font-size:14px;overflow-wrap:anywhere}.src h4{font-size:13px;color:#5d7a98;margin:12px 0 4px}.src table{border-collapse:collapse;width:100%;font-size:12px}
.src th,.src td{border:1px solid #dfe7ef;padding:6px 8px;text-align:left}.src th{background:#f2f6fa}.src svg{display:block;max-width:100%;height:auto;margin:10px auto}
figure{margin:12px 0;text-align:center}figure svg{max-width:420px;width:100%;height:auto;border:1px solid #e5eaf0;border-radius:10px}figcaption{font-size:11px;color:#8193a4}
.yt{font-size:12px}.yt a{color:#d8322a}@media(max-width:640px){nav{columns:1}}"""


def _chart_svg(job: Job, sid: str) -> str:
    sh = job.short(sid) or {}
    for n, im in enumerate(sh.get("images") or [], 1):
        if im.get("role") == "chart":
            p = job.sub("images", sid) / f"{n:02d}.svg"
            if p.exists():
                return p.read_text(encoding="utf-8")
    return ""


def run(job: Job) -> None:
    from .terms import load as load_terms
    state = job.state()
    units = [u for u in job.units if u.is_html]
    if not units:
        raise SystemExit("HTML 원고(용어 모드) 단원이 없어요.")
    toc: List[str] = []
    body: List[str] = []
    total = 0
    for u in units:
        terms = load_terms(u).get("terms") or []
        if not terms:
            continue
        doc = u.doc()
        src: Dict[str, Any] = {s["id"]: s for s in doc["sources"]}
        body.append(f'<h2 id="u{html.escape(u.prefix)}">{html.escape(u.prefix)} {html.escape(u.section)}</h2>')
        toc.append(f'<div><a href="#u{html.escape(u.prefix)}">{html.escape(u.prefix)} {html.escape(u.section)}</a> · {len(terms)}</div>')
        for t in terms:
            total += 1
            parts = [f'<section class="term" id="{html.escape(t["sid"])}"><h3>{html.escape(t["name"])}<span class="sid">{html.escape(t["sid"])}</span></h3>']
            url = ((state.get(t["sid"]) or {}).get("posted") or {}).get("url")
            if url:
                parts.append(f'<div class="yt">▶ 쇼츠: <a href="{html.escape(url)}">{html.escape(url)}</a></div>')
            chart = _chart_svg(job, t["sid"])
            if chart:
                parts.append(f"<figure>{chart}<figcaption>쇼츠 개념 도식</figcaption></figure>")
            parts.append('<div class="src">')
            for sid in t["sources"]:
                s = src.get(sid)
                if s:
                    parts.append(f"<h4>{html.escape(s['title'])}</h4>{s['body']}{''.join(s['svgs'])}")
            parts.append("</div></section>")
            body.append("".join(parts))
    page = (f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{html.escape(job.get("title", job.name))} 용어집</title><style>{CSS}</style></head><body><div class="wrap">'
            f'<h1>{html.escape(job.get("title", job.name))} 용어집</h1><div class="meta">용어 {total}개 · 원문은 원고 그대로</div>'
            f'<nav>{"".join(toc)}</nav>{"".join(body)}</div></body></html>')
    out = job.dir / "glossary.html"
    out.write_text(page, encoding="utf-8")
    log(f"✓ 용어집 {total}개 → {out}")
