"""생성 도식 SVG 정리 — 화살촉 크기 고정 + 선을 끊어 보이게 하는 라벨 배경 제거.

  ① <marker> 는 기본 markerUnits="strokeWidth" 라 선 굵기(2~4)만큼 촉이 2~4배로 커진다.
     → viewBox 로 모양을 보존하고 markerUnits="userSpaceOnUse", 촉 크기 = 선 굵기 × ARROW_RATIO(최소·최대 제한).
  ② 화살표 라벨 뒤에 깐 흰 사각형(mask rect)이 선 위에 놓이면 선이 두 동강 나 보인다.
     → 그 사각형을 지우고, 라벨이 선 위에 있으면 선 옆(GAP px)으로 비킨 뒤 글자에만 얇은 흰 후광(paint-order)을 준다.
원고에 원래 있던 SVG(정량 그래프)에는 쓰지 않는다 — 생성 도식에만.
"""
from __future__ import annotations

import re
import statistics
import unicodedata
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple

SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)
ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")

ARROW_RATIO = 4.0           # 촉 길이 ≈ 선 굵기 × 4
GAP = 8                     # 라벨과 선 사이
PAPER = {"#fff", "#ffffff", "white", "#f5f5f5", "#fafafa", "#fcfcfc", "#fefefe", "#f8fafc"}
HALO = {"paint-order": "stroke", "stroke": "#ffffff", "stroke-linejoin": "round"}

Seg = Tuple[float, float, float, float]
Box = Tuple[float, float, float, float]        # x0, y0, x1, y1


def _tag(el: ET.Element) -> str:
    return el.tag.rsplit("}", 1)[-1]


def _num(v: Optional[str], default: float = 0.0) -> float:
    m = re.match(r"\s*(-?[\d.]+(?:e-?\d+)?)", str(v or ""))
    return float(m.group(1)) if m else default


def _style(el: ET.Element, key: str) -> Optional[str]:
    """속성 또는 style="…" 안의 값."""
    if el.get(key) is not None:
        return el.get(key)
    m = re.search(rf"(?:^|;)\s*{re.escape(key)}\s*:\s*([^;]+)", el.get("style") or "")
    return m.group(1).strip() if m else None


def _translate(el: ET.Element) -> Optional[Tuple[float, float]]:
    """translate 만 따라간다. 회전·배율이 있으면 None(그 아래는 기하 계산을 건너뜀)."""
    t = (el.get("transform") or "").strip()
    if not t:
        return 0.0, 0.0
    m = re.fullmatch(r"translate\(\s*(-?[\d.]+)(?:[\s,]+(-?[\d.]+))?\s*\)", t)
    return (float(m.group(1)), float(m.group(2) or 0)) if m else None


# ── ① 화살촉 ────────────────────────────────────────────────────────────────
def _marker_ids(root: ET.Element) -> Dict[str, List[float]]:
    """marker id → 그 마커를 쓰는 선들의 굵기."""
    out: Dict[str, List[float]] = {}
    for el in root.iter():
        for k in ("marker-end", "marker-start", "marker-mid"):
            v = _style(el, k)
            m = re.search(r"url\(#([^)]+)\)", v or "")
            if m:
                out.setdefault(m.group(1), []).append(_num(_style(el, "stroke-width"), 1.0))
    return out


def fix_markers(root: ET.Element, *, min_len: float = 6, max_len: float = 22) -> int:
    users = _marker_ids(root)
    n = 0
    for mk in root.iter(f"{{{SVG_NS}}}marker"):
        w, h = _num(mk.get("markerWidth"), 3), _num(mk.get("markerHeight"), 3)
        if w <= 0 or h <= 0:
            continue
        units = mk.get("markerUnits", "strokeWidth")
        stroke = statistics.median(users.get(mk.get("id", ""), [1.0]) or [1.0])
        cur_len = w * (stroke if units == "strokeWidth" else 1)
        want = max(min_len, min(max_len, stroke * ARROW_RATIO))
        if units == "userSpaceOnUse" and cur_len <= max(want * 1.25, min_len):
            continue
        if not mk.get("viewBox"):
            mk.set("viewBox", f"0 0 {w:g} {h:g}")
        mk.set("markerUnits", "userSpaceOnUse")
        mk.set("markerWidth", f"{want:.1f}")
        mk.set("markerHeight", f"{want * h / w:.1f}")
        n += 1
    return n


# ── ② 라벨 ───────────────────────────────────────────────────────────────────
def _path_segs(d: str, ox: float, oy: float) -> List[Seg]:
    """M/L/H/V/Q/C/A 끝점만 이은 꺾은선 근사(도식 연결선은 직각선이 대부분)."""
    segs: List[Seg] = []
    toks = re.findall(r"[MmLlHhVvQqCcAaZzTtSs]|-?[\d.]+(?:e-?\d+)?", d or "")
    x = y = sx = sy = 0.0
    cmd, i = "M", 0
    arity = {"M": 2, "L": 2, "T": 2, "H": 1, "V": 1, "Q": 4, "S": 4, "C": 6, "A": 7}
    while i < len(toks):
        if re.match(r"[A-Za-z]", toks[i]):
            cmd = toks[i]
            i += 1
            if cmd in "Zz":
                segs.append((x, y, sx, sy))
                x, y = sx, sy
                continue
        up, rel = cmd.upper(), cmd.islower()
        k = arity.get(up, 2)
        vals = [float(v) for v in toks[i:i + k]]
        if len(vals) < k:
            break
        i += k
        if up == "H":
            nx, ny = (x + vals[0] if rel else vals[0]), y
        elif up == "V":
            nx, ny = x, (y + vals[0] if rel else vals[0])
        else:
            nx, ny = vals[-2], vals[-1]
            if rel:
                nx, ny = x + nx, y + ny
        if up == "M":
            sx, sy = nx, ny
            cmd = "l" if rel else "L"
        else:
            segs.append((x, y, nx, ny))
        x, y = nx, ny
    return [(a + ox, b + oy, c + ox, e + oy) for a, b, c, e in segs]


def _walk(el: ET.Element, ox: float, oy: float, out: List[Tuple[ET.Element, ET.Element, float, float]], parent=None):
    t = _translate(el)
    if t is None:
        return
    ox, oy = ox + t[0], oy + t[1]
    if parent is not None:
        out.append((el, parent, ox, oy))
    if _tag(el) in ("defs", "marker", "clipPath", "title", "desc"):
        return
    for ch in list(el):
        _walk(ch, ox, oy, out, el)


def _connectors(items) -> List[Seg]:
    segs: List[Seg] = []
    for el, _p, ox, oy in items:
        tag = _tag(el)
        has_marker = any(_style(el, k) for k in ("marker-end", "marker-start"))
        fill = (_style(el, "fill") or "").lower()
        if tag == "line":
            segs.append((_num(el.get("x1")) + ox, _num(el.get("y1")) + oy, _num(el.get("x2")) + ox, _num(el.get("y2")) + oy))
        elif tag == "path" and (has_marker or fill in ("none", "transparent")):
            segs += _path_segs(el.get("d", ""), ox, oy)
        elif tag == "polyline" and (has_marker or fill in ("none", "transparent", "")):
            pts = [float(v) for v in re.findall(r"-?[\d.]+", el.get("points", ""))]
            xy = list(zip(pts[::2], pts[1::2]))
            segs += [(a[0] + ox, a[1] + oy, b[0] + ox, b[1] + oy) for a, b in zip(xy, xy[1:])]
    return segs


def _hits(seg: Seg, box: Box) -> bool:
    x0, y0, x1, y1 = box
    a, b, c, d = seg
    if abs(b - d) < 0.5:            # 가로선
        return y0 <= b <= y1 and min(a, c) < x1 and max(a, c) > x0
    if abs(a - c) < 0.5:            # 세로선
        return x0 <= a <= x1 and min(b, d) < y1 and max(b, d) > y0
    for k in range(21):             # 사선 — 표본점
        px, py = a + (c - a) * k / 20, b + (d - b) * k / 20
        if x0 <= px <= x1 and y0 <= py <= y1:
            return True
    return False


def _text_width(s: str, fs: float) -> float:
    return sum((1.0 if unicodedata.east_asian_width(ch) in "WF" else 0.6) for ch in s) * fs


def _text_box(el: ET.Element, ox: float, oy: float) -> Optional[Box]:
    if any(_tag(c) == "tspan" and (c.get("y") or c.get("dy")) for c in el):
        return None                 # 여러 줄 라벨은 건드리지 않는다
    fs = _num(_style(el, "font-size"), 12)
    s = "".join(el.itertext()).strip()
    if not s:
        return None
    x, y = _num(el.get("x")) + ox, _num(el.get("y")) + oy
    w = _text_width(s, fs)
    anchor = _style(el, "text-anchor") or "start"
    x0 = x - w / 2 if anchor == "middle" else x - w if anchor == "end" else x
    base = _style(el, "dominant-baseline") or ""
    top = y - fs * 0.5 if "middle" in base or "central" in base else y - fs * 0.85
    return x0, top, x0 + w, top + fs * 1.05


def _halo(el: ET.Element, fs: float) -> None:
    for k, v in HALO.items():
        el.set(k, v)
    el.set("stroke-width", f"{max(3.0, fs * 0.28):.1f}")


def _is_paper_rect(el: ET.Element) -> bool:
    fill = (_style(el, "fill") or "").lower().replace(" ", "")
    stroke = (_style(el, "stroke") or "none").lower()
    return _tag(el) == "rect" and fill in PAPER and stroke in ("none", "transparent", "")


def fix_labels(root: ET.Element) -> int:
    items: List[Tuple[ET.Element, ET.Element, float, float]] = []
    _walk(root, 0, 0, items)
    segs = _connectors(items)
    if not segs:
        return 0
    n = 0
    for el, parent, ox, oy in items:
        if _tag(el) != "text":
            continue
        box = _text_box(el, ox, oy)
        if not box:
            continue
        fs = _num(_style(el, "font-size"), 12)
        sibs = list(parent)
        k = sibs.index(el)
        prev = sibs[k - 1] if k > 0 else None
        mask = None
        if prev is not None and _is_paper_rect(prev):
            px, py = _num(prev.get("x")) + ox, _num(prev.get("y")) + oy
            rb = (px, py, px + _num(prev.get("width")), py + _num(prev.get("height")))
            cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
            if rb[0] - 2 <= cx <= rb[2] + 2 and rb[1] - 2 <= cy <= rb[3] + 2 and (rb[3] - rb[1]) <= fs * 2.6:
                mask = (prev, rb)
        on_line = [s for s in segs if _hits(s, (box[0] - 1, box[1] - 1, box[2] + 1, box[3] + 1))]
        mask_hits = mask and any(_hits(s, mask[1]) for s in segs)
        if not on_line and not mask_hits:
            continue
        if mask:
            parent.remove(mask[0])
        if on_line:
            s = on_line[0]
            if abs(s[1] - s[3]) < 0.5:          # 가로선 → 글자를 선 위로
                line_y = s[1]
                shift = (line_y - GAP) - (box[3] - fs * 0.05)
                el.set("y", f"{_num(el.get('y')) + shift:.1f}")
            elif abs(s[0] - s[2]) < 0.5:        # 세로선 → 글자를 선 오른쪽으로
                line_x = s[0]
                el.set("text-anchor", "start")
                el.set("x", f"{line_x + GAP - ox:.1f}")
        _halo(el, fs)
        n += 1
    return n


# ── 진입점 ───────────────────────────────────────────────────────────────────
def _parse(svg: str) -> Optional[ET.Element]:
    try:
        root = ET.fromstring(svg)
    except ET.ParseError:
        return None
    return root if _tag(root) == "svg" and root.tag.startswith(f"{{{SVG_NS}}}") else None


def tidy(svg: str, *, arrow_min: float = 6, arrow_max: float = 22) -> Tuple[str, Dict[str, int]]:
    """(정리된 SVG, {"markers": 고친 수, "labels": 고친 수}). XML 로 못 읽으면 마커만 정규식으로."""
    svg = svg.strip()
    if "xmlns=" not in svg[:300]:
        svg = svg.replace("<svg", f'<svg xmlns="{SVG_NS}"', 1)
    root = _parse(svg)
    if root is None:
        return _regex_markers(svg), {"markers": -1, "labels": 0}
    rep = {"markers": fix_markers(root, min_len=arrow_min, max_len=arrow_max), "labels": fix_labels(root)}
    return ET.tostring(root, encoding="unicode"), rep


def _regex_markers(svg: str) -> str:
    def one(m: re.Match) -> str:
        tag = m.group(0)
        if "markerUnits" in tag:
            return tag
        w = re.search(r'markerWidth="([\d.]+)"', tag)
        h = re.search(r'markerHeight="([\d.]+)"', tag)
        if not (w and h):
            return tag
        vb = "" if "viewBox" in tag else f' viewBox="0 0 {w.group(1)} {h.group(1)}"'
        return tag[:-1] + f'{vb} markerUnits="userSpaceOnUse">'
    return re.sub(r"<marker\b[^>]*>", one, svg)
