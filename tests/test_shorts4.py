"""쇼츠공방4 회귀 테스트 — `.venv\\Scripts\\python -m pytest -q tests` (pytest 없으면 `python tests/test_shorts4.py`)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aside_shorts import svgfix  # noqa: E402

SVG = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 200">
<defs><marker id="a" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto"><polygon points="0 0, 8 3, 0 6"/></marker></defs>
<path d="M 20 100 L 380 100" stroke="#333" stroke-width="3" fill="none" marker-end="url(#a)"/>
<rect x="170" y="90" width="60" height="20" fill="#ffffff"/><text x="200" y="105" font-size="14" text-anchor="middle">참조</text>
<line x1="300" y1="10" x2="300" y2="90" stroke="#333" stroke-width="2"/><text x="300" y="50" font-size="12" text-anchor="middle">FK</text>
<rect x="20" y="140" width="120" height="40" fill="#DEEBF7" stroke="#1F4E79"/><text x="80" y="165" font-size="14" text-anchor="middle">노드</text>
</svg>'''


def test_marker_fixed_size():
    out, rep = svgfix.tidy(SVG)
    assert rep["markers"] == 1
    assert 'markerUnits="userSpaceOnUse"' in out and 'viewBox="0 0 8 6"' in out
    assert 'markerWidth="12.0"' in out          # 선 굵기 3 × 4


def test_label_mask_removed_and_moved_beside_line():
    out, rep = svgfix.tidy(SVG)
    assert rep["labels"] == 2
    assert 'width="60"' not in out              # 선 위의 흰 사각형 제거
    assert 'y="89.9"' in out                     # 가로선 위로 비킴
    assert 'x="308.0"' in out and 'text-anchor="start"' in out   # 세로선 오른쪽으로
    assert out.count('paint-order="stroke"') == 2


def test_node_text_untouched():
    out, _ = svgfix.tidy(SVG)
    assert '<text x="80" y="165" font-size="14" text-anchor="middle">' in out


def test_already_fine_marker_kept():
    ok = SVG.replace('markerWidth="8"', 'viewBox="0 0 8 6" markerUnits="userSpaceOnUse" markerWidth="12"').replace('markerHeight="6"', 'markerHeight="9"', 1)
    _, rep = svgfix.tidy(ok)
    assert rep["markers"] == 0


def test_html_manuscripts_split():
    from aside_shorts import html_manuscript as hm
    files = sorted((ROOT / "_context").glob("*.html"))
    if not files:
        return
    for f in files:
        chs = hm.split_chapters(f.read_text(encoding="utf-8"))
        assert chs and all(hm.parse_document(page, "x")["sources"] for _, _, page in chs)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
