"""원고 — 절(1장 2절) 하나 = 단원 폴더 하나.

jobs/<job>/<장>-<절>_<절 제목>/          예: 1-2_통합적 관점의 필요성과 적용
  01_raw/<원본>.docx       교과서 원문 — **보관만, 절대 고치지 않는다**
  02_rewrite/<원본>.docx   안전 개작본(개념·정의 유지, 사례 교체) + 검증.json   ← s0-rewrite
  03_script/<id>.json      관점별 쇼츠 대본(s1) · <id>.edit.json(사람 수정)
  04_bundle/<id>/          쇼츠 한 편의 모든 것: audio/ images/ motion/ out/<id>.mp4

쇼츠 번호 <장>-<절>-<NN> (예: 1-2-04 = 1장 2절의 4번째 관점).
원고 파일 이름 `<N>장_<장 제목>-<M>절_<절 제목>.docx` 에서 장·절을 읽는다.

HTML 원고(SQLD 등, h1 문서 · h2 장 · h3 소주제)는 **용어 모드**:
  h2 장 하나 = 단원 폴더 하나 `<책>-<장>_<장 제목>/01_raw/<책>-<장>.html` (책 = 파일 이름 앞 숫자, 예: 2summary-sql → 2)
  02_terms/terms.json  용어 목록(s0-terms) — 용어 하나 = 쇼츠 한 편, 번호 <책>-<장>-<NN>
  자체 원고로 보고 안전 개작은 하지 않는다 — 대본은 01_raw 를 바로 쓴다.
"""
from __future__ import annotations

import hashlib
import html
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

EXTS = (".docx", ".txt", ".md", ".html")
RAW, REWRITE, SCRIPT, BUNDLE = "01_raw", "02_rewrite", "03_script", "04_bundle"
TERMS = "02_terms"
_NAME = re.compile(r"^\s*(\d+)\s*장[_\s]*(.*?)\s*-\s*(\d+)\s*절[_\s]*(.*)$")
_NAME2 = re.compile(r"^\s*(\d+)\s+(.+?)\s*-\s*(\d+)\s*(.*)$")       # 「2 장제목-1 절제목」
_UNIT = re.compile(r"^(\d+)-(\d+)_(.*)$")


def docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as zf:
        xml = zf.read("word/document.xml").decode("utf-8", errors="replace")
    xml = re.sub(r"</w:p>", "\n", xml)
    xml = re.sub(r"<w:br\s*/?>", "\n", xml)
    xml = re.sub(r"<w:tab\s*/?>", "\t", xml)
    text = html.unescape(re.sub(r"<[^>]+>", "", xml))
    text = re.sub(r"[ \t]+\n", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def read_text(path: Path) -> str:
    if path.suffix.lower() == ".docx":
        return docx_text(path)
    if path.suffix.lower() == ".html":
        from .html_manuscript import parse_document
        doc = parse_document(path.read_text(encoding="utf-8"), path.name)
        return "\n\n".join(f"{s['title']}\n{s['text']}" for s in doc["sources"])
    return path.read_text(encoding="utf-8", errors="ignore").strip()


def parse_name(stem: str) -> Optional[tuple]:
    """'1장_통합적 관점-2절_통합적 관점의 필요성과 적용' → ('1-2', '1장 통합적 관점', '2절 통합적 관점의 필요성과 적용')

    「장」「절」 글자가 없는 꼴도 읽는다(2026-10-05 실제 원고 이름):
      '2 인간,사회,환경과행복-1 행복의 기준과 의미'  → 2장 1절
      '4 문화의 다양성 - 2 문화 변동의 양상'          → 4장 2절
      '3 자연환경과 인간-4환경 문제의 발생과 …'       → 3장 4절"""
    m = _NAME.match(stem) or _NAME2.match(stem)
    if not m:
        return None
    ch, ch_t, sec, sec_t = m.groups()
    return f"{int(ch)}-{int(sec)}", f"{int(ch)}장 {ch_t}".strip(), f"{int(sec)}절 {sec_t}".strip()


def unit_dirname(prefix: str, section_title: str) -> str:
    t = re.sub(r"^\d+절\s*", "", section_title).strip()
    t = re.sub(r'[\\/:*?"<>|]', "", t)[:40].strip()
    return f"{prefix}_{t}" if t else prefix


def _docs_in(d: Path) -> List[Path]:
    if not d.exists():
        return []
    return sorted(p for p in d.iterdir() if p.suffix.lower() in EXTS and not p.name.startswith("~$"))


@dataclass
class Unit:
    dir: Path
    prefix: str             # "1-2"
    chapter: str            # "1장 통합적 관점"
    section: str            # "2절 통합적 관점의 필요성과 적용"

    @property
    def raw(self) -> Optional[Path]:
        f = _docs_in(self.dir / RAW)
        return f[0] if f else None

    @property
    def rewrite(self) -> Optional[Path]:
        f = _docs_in(self.dir / REWRITE)
        return f[0] if f else None

    @property
    def is_html(self) -> bool:
        return bool(self.raw and self.raw.suffix.lower() == ".html")

    @property
    def source(self) -> Optional[Path]:
        """대본(s1)의 재료 — **개작본만**. 원문은 쓰지 않는다. (HTML 원고는 자체 원고라 원본을 바로)"""
        return self.raw if self.is_html else self.rewrite

    def doc(self) -> dict:
        """HTML 원고를 termbook 구조(sources = h3 소주제들)로."""
        from .html_manuscript import parse_document
        return parse_document(self.raw.read_text(encoding="utf-8"), self.raw.name)

    @property
    def terms_dir(self) -> Path:
        return self.dir / TERMS

    @property
    def text(self) -> str:
        return read_text(self.source) if self.source else ""

    @property
    def hash(self) -> str:
        return hashlib.sha1(self.text.encode("utf-8")).hexdigest()[:12]

    @property
    def script_dir(self) -> Path:
        return self.dir / SCRIPT

    @property
    def bundle_dir(self) -> Path:
        return self.dir / BUNDLE

    @property
    def name(self) -> str:
        return self.dir.name


def units_in(job_dir: Path) -> List[Unit]:
    out = []
    if not job_dir.exists():
        return out
    for d in sorted(job_dir.iterdir(), key=lambda p: [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", p.name)]):
        m = _UNIT.match(d.name)
        if not d.is_dir() or not m:
            continue
        prefix = f"{int(m.group(1))}-{int(m.group(2))}"
        any_doc = (_docs_in(d / RAW) or _docs_in(d / REWRITE) or [None])[0]
        meta = parse_name(any_doc.stem) if any_doc and any_doc.suffix.lower() != ".html" else None
        ch, sec = (meta[1], meta[2]) if meta else ("", m.group(3))
        if any_doc and any_doc.suffix.lower() == ".html":
            h1 = re.search(r"<h1[^>]*>(.*?)</h1>", any_doc.read_text(encoding="utf-8"), re.S)
            ch = html.unescape(re.sub(r"<[^>]+>", "", h1.group(1))).strip() if h1 else ""
        out.append(Unit(d, prefix, ch, sec))
    return out


# ── 가져오기 ─────────────────────────────────────────────────────────────────
def classify_sources(src: Path) -> List[dict]:
    """--from 에 준 곳에서 원고를 찾아 [{file, stage: raw|rewrite}] 로.

    260711 형식(절 폴더 안의 01_raw · 02_)이면 01_raw → 원본, 02_ → 개작본으로 나눠 둘 다 가져온다.
    그냥 폴더·파일이면 모두 **원본**(s0-rewrite 가 개작본을 만든다)."""
    src = Path(src)
    if src.is_file():
        return [{"file": src, "stage": "raw"}]
    if not src.is_dir():
        return []
    out = []
    raw_dirs = [p for p in src.rglob("01_raw") if p.is_dir()]
    rw_dirs = [p for p in src.rglob("02_") if p.is_dir()]
    if raw_dirs or rw_dirs:
        for d in raw_dirs:
            out += [{"file": p, "stage": "raw"} for p in _docs_in(d) if "복사본" not in p.stem]
        for d in rw_dirs:
            out += [{"file": p, "stage": "rewrite"} for p in _docs_in(d) if "복사본" not in p.stem]
        return out
    return [{"file": p, "stage": "raw"} for p in _docs_in(src)]


def place_html(job_dir: Path, file: Path, n: int = 1) -> List[Path]:
    """HTML 원고 하나 → h2 장마다 단원 폴더 `<책>-<장>_<장 제목>/01_raw/<책>-<장>.html`."""
    from .html_manuscript import split_chapters
    m = re.match(r"\s*(\d+)", file.stem)
    book = int(m.group(1)) if m else n
    out = []
    for c, title, page in split_chapters(file.read_text(encoding="utf-8")):
        prefix = f"{book}-{c}"
        unit = next((u for u in units_in(job_dir) if u.prefix == prefix), None)
        name = re.sub(r"^\d+(?:\.\d+)*\.?\s*", "", title)
        d = unit.dir if unit else job_dir / unit_dirname(prefix, name)
        target = d / RAW
        target.mkdir(parents=True, exist_ok=True)
        f = target / f"{prefix}.html"
        f.write_text(page, encoding="utf-8")
        out.append(f)
    return out


def place(job_dir: Path, file: Path, stage: str, n: int = 1) -> Path:
    """원고 하나를 단원 폴더의 01_raw 또는 02_rewrite 에 복사한다. 단원 폴더가 없으면 만든다."""
    import shutil
    meta = parse_name(file.stem)
    prefix, sec = (meta[0], meta[2]) if meta else (f"0-{n}", file.stem)
    unit = next((u for u in units_in(job_dir) if u.prefix == prefix), None)
    d = unit.dir if unit else job_dir / unit_dirname(prefix, sec)
    target = d / (RAW if stage == "raw" else REWRITE)
    target.mkdir(parents=True, exist_ok=True)
    for old in _docs_in(target):          # 단계 폴더 하나에 원고는 하나
        if old.name != file.name:
            old.unlink()
    out = target / file.name
    shutil.copy2(file, out)
    return out
