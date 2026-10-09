"""유튜브 업로드 문구 — 제목(+해시태그)·설명(후크 2줄·해시태그·소제목·개념 설명)·태그·고정 댓글.

@dekmanfactory 기존 쇼츠 형식을 따르되, 설명란 개념 글은 **원고와 전혀 다른 글**이어야 한다.
그래서 코드가 원본(01_raw)·개작본(02_rewrite)과 비교해 검사하고, 걸리면 Claude 에게 다시 쓰게 한다:
  · 원고와 띄어쓰기 빼고 MAX_RUN(15)자 넘게 같은 구간이 있으면 안 됨
  · 설명 문단과 원고 문단의 유사도(difflib)가 MAX_SIM(0.5)을 넘으면 안 됨
결과는 대본 JSON 의 `youtube` 칸에 저장(사람이 고친 것은 .edit.json 이 이김). s1 이 대본을 쓴 뒤 부른다.
따로 다시 쓰기: `run.bat yt-meta --job J [--only 1-2-03] [--force]`
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any, Dict, List

from . import config
from .job import Job
from .llm import claude_cli
from .log import detail, log
from .manuscript import read_text

PROMPT = config.ROOT / "aside_shorts" / "prompts" / "ytmeta.md"
MAX_RUN = 15
MAX_SIM = 0.5
_STR = {"type": "string"}
_ARR = {"type": "array", "items": _STR}
SCHEMA = {"type": "object", "required": ["items"], "properties": {"items": {"type": "array", "items": {
    "type": "object",
    "required": ["id", "title", "title_tags", "hook_lines", "desc_tags", "section_label", "summary", "tags", "pinned_comment"],
    "properties": {"id": _STR, "title": _STR, "title_tags": _ARR, "hook_lines": _ARR, "desc_tags": _ARR,
                   "section_label": _STR, "summary": _ARR, "tags": _ARR, "pinned_comment": _STR}}}}}
# 개작 소제목이 있는 쇼츠: 설명 본문 = 그 소제목의 개작 글(이미 원문과 다른지 검사됨) — Claude 는 나머지만 쓴다
SCHEMA_SEC = {"type": "object", "required": ["items"], "properties": {"items": {"type": "array", "items": {
    "type": "object", "required": ["id", "title", "title_tags", "hook_lines", "desc_tags", "tags", "pinned_comment"],
    "properties": {"id": _STR, "title": _STR, "title_tags": _ARR, "hook_lines": _ARR, "desc_tags": _ARR,
                   "tags": _ARR, "pinned_comment": _STR}}}}}


def _squash(t: str) -> str:
    return re.sub(r"\s+", "", t or "")


def longest_run(a: str, b: str) -> tuple:
    """(길이, 겹친 글자) — 띄어쓰기 무시."""
    a, b = _squash(a), _squash(b)
    m = SequenceMatcher(None, a, b, autojunk=False).find_longest_match(0, len(a), 0, len(b))
    return m.size, a[m.a:m.a + m.size]


def check(item: Dict[str, Any], sources: List[str]) -> List[str]:
    probs = []
    paras = [p for s in sources for p in s.splitlines() if len(p.strip()) > 20]
    for k, para in enumerate(item.get("summary") or [], 1):
        for src in sources:
            n, frag = longest_run(para, src)
            if n > MAX_RUN:
                probs.append(f"{item['id']} 설명 {k}문단이 원고와 {n}자 겹침: 「{frag[:40]}」 — 완전히 다른 표현으로")
                break
        sim = max((SequenceMatcher(None, para, p).ratio() for p in paras), default=0)
        if sim > MAX_SIM:
            probs.append(f"{item['id']} 설명 {k}문단이 원고 문단과 비슷함(유사도 {sim:.2f}) — 문장 구조부터 새로")
    if len(item.get("hook_lines") or []) < 2:
        probs.append(f"{item['id']} hook_lines 는 2줄")
    return probs


def _brief(job: Job, unit, ids: List[str]) -> str:
    out = [f"[교과] {job.get('title', '')}", f"[단원] {unit.chapter} / {unit.section}", "", "[원고 — 이 문장들을 옮기지 말 것]", unit.text, ""]
    for n, sid in enumerate(ids, 1):
        sh = job.short(sid) or {}
        out += [f"## {sid} (단원 안 {n}번째) — {sh.get('perspective', '')}",
                f"후크: {(sh.get('hook') or {}).get('line1', '')} / {(sh.get('hook') or {}).get('line2', '')}",
                "대사: " + " ".join(ln.get("text", "") for ln in sh.get("lines") or [])]
        q = sh.get("quiz") or {}
        if q:
            out.append(f"영상 끝 퀴즈: {q.get('question', '')} → 정답 {q.get('answer', '')} ({q.get('explain', '')})")
        out.append("")
    return "\n".join(out)


TERM_RULES = """

# 이번 쇼츠는 {EXAM} 용어 쇼츠다 (위 형식보다 이 규칙이 우선)
- 채널 주제는 {EXAM} 자격증. 통합사회·교과 표현을 쓰지 않는다.
- `title`: **용어 이름을 맨 앞에**(검색 노출) + 궁금증 한 줄, 28자 안팎. 예: "TRUNCATE, DELETE랑 같은 편 아닙니다", "HAVING vs WHERE 30초 정리".
- `title_tags`: {EXAM}(띄어쓰기 없이), 자격증, 그 과목 분야어, 그 용어, 관련 개념어 섞어 10~12개.
- `section_label`: 장 번호와 용어, 예: "1장 · TRUNCATE".
- `summary`: 시험 포인트 위주 3~4문단(정의 → 헷갈리는 지점 → 시험에서 이렇게 나온다 → 한 줄 암기).
- `pinned_comment`: **영상 끝 퀴즈의 정답**과 한 줄 해설(정답은 설명란 맨 위에도 코드가 따로 싣는다). 예: "정답: X — TRUNCATE 는 DDL 이라 실행 즉시 커밋돼서 롤백할 수 없어요. 헷갈렸던 분은 👍".
- 원고는 자체 원고다 — 겹침 걱정 없이 정확한 용어·정의를 그대로 써도 된다. 단 원고에 없는 내용은 지어내지 않는다."""


def _sections_for(job: Job, unit, ids: List[str]) -> Dict[str, Dict[str, Any]]:
    from .s0_rewrite import load_sections
    secs = (load_sections(unit) or {}).get("sections") or []
    out = {}
    for sid in ids:
        idx = ((job.raw_short(sid) or {}).get("section") or {}).get("index")
        if idx and idx <= len(secs):
            out[sid] = secs[idx - 1]
    return out


def write_unit(job: Job, unit, ids: List[str], *, model: str) -> int:
    """단원 하나의 쇼츠들 문구를 쓰고 검사해 저장. 남은 문제 수를 돌려준다."""
    if not ids:
        return 0
    sources = [read_text(p) for p in (unit.raw, unit.rewrite) if p]
    system = PROMPT.read_text(encoding="utf-8")
    if unit.is_html:            # SQLD 용어 모드 — 자체 원고라 겹침 검사 안 함
        system += TERM_RULES.replace("{EXAM}", job.get("exam") or job.get("title") or "SQLD")
        sources = []
    secmap = _sections_for(job, unit, ids) if not unit.is_html else {}
    use_sec = len(secmap) == len(ids)
    schema = SCHEMA_SEC if use_sec else SCHEMA
    if use_sec:
        system += ("\n\n# 이번 쇼츠들은 설명 본문(section_label·summary)이 이미 정해져 있다 — 그 칸은 쓰지 않는다.\n"
                   "hook_lines·title 은 그 본문 내용과 맞춰라.")
        sources = []            # 본문을 Claude 가 쓰지 않으니 겹침 검사 대상이 없다(개작 단계에서 이미 검사)
    prompt = _brief(job, unit, ids)
    if use_sec:
        prompt += "\n[편마다 설명 본문으로 쓰일 개작 글]\n" + "\n".join(
            f"{sid}: {secmap[sid]['label']}\n" + "\n".join(secmap[sid].get("paragraphs") or []) for sid in ids)
    res = claude_cli.structured(prompt, system, schema, model=model)
    items = {it.get("id"): it for it in res.get("items") or []}
    probs = [p for sid in ids if sid in items for p in check(items[sid], sources)]
    missing = [sid for sid in ids if sid not in items]
    if probs or missing:
        log(f"  유튜브 문구가 원고와 겹치거나 빠진 곳이 {len(probs) + len(missing)}군데 — Claude 에게 다시 맡겨요 …")
        detail(f"  ytmeta 1차 문제: {probs} 빠짐 {missing}")
        fix = prompt + "\n\n[앞선 결과의 문제 — 모두 고쳐서 전체를 다시]\n- " + "\n- ".join(probs + [f"{m} 빠짐" for m in missing])
        res = claude_cli.structured(fix, system, schema, model=model)
        items = {it.get("id"): it for it in res.get("items") or []}
    left = 0
    for sid in ids:
        it = items.get(sid)
        if not it:
            left += 1
            continue
        if use_sec:
            it["section_label"] = secmap[sid]["label"]
            it["summary"] = list(secmap[sid].get("paragraphs") or [])
            it["summary_from"] = "02_rewrite"
        p = check(it, sources)
        left += len(p)
        it = {k: v for k, v in it.items() if k != "id"}
        it["check"] = {"passed": not p, "problems": p, "max_run": MAX_RUN, "max_sim": MAX_SIM}
        path = job.script_path(sid)
        sh = config.read_json(path) or {}
        sh["youtube"] = it
        config.write_json(path, sh)
        log(f"  {'✓' if not p else '△'} {sid} 유튜브 문구 — {it.get('title', '')}" + (f" (겹침 {len(p)}건 남음)" if p else ""))
    return left


def run(job: Job, only=None, force: bool = False, **_) -> None:
    model = config.load()["claude"]["script_model"]
    ids = job.pick(only)
    for u in job.units:
        mine = [s for s in ids if s.startswith(u.prefix + "-")]
        if not force:
            mine = [s for s in mine if "hook_lines" not in ((job.raw_short(s) or {}).get("youtube") or {})]
        if mine:
            log(f"「{u.section or u.name}」 유튜브 문구를 쓰는 중이에요 ({len(mine)}편) …")
            write_unit(job, u, mine, model=model)
