"""s1-script — 원고(절 하나)를 Claude 가 관점별 쇼츠 대본 여러 편으로 나눠 쓴다.

결과: shorts/<장>-<절>-<NN>.json 하나에 한 편(후크·문장·그림 목록·유튜브 메타).
캐시: shorts/_s1.json 에 원고 해시를 적어 두고, 원고가 그대로면 건너뛴다(--force 로 다시).
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from . import config
from .job import Job
from .llm import claude_cli
from .log import detail, log

PROMPT = config.ROOT / "aside_shorts" / "prompts" / "shorts_script.md"
TERM_PROMPT = config.ROOT / "aside_shorts" / "prompts" / "term_script.md"
TERM_BATCH = 4          # 용어 모드: Claude 한 번에 용어 몇 개씩

_STR = {"type": "string"}
SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": ["unit_title", "unit_topic", "shorts"],
    "properties": {"unit_title": _STR, "unit_topic": _STR, "shorts": {"type": "array", "minItems": 1, "items": {
        "type": "object",
        "required": ["perspective", "hook", "lines", "images"],
        "properties": {
            "perspective": _STR,
            "hook": {"type": "object", "required": ["line1", "line2"],
                     "properties": {"line1": _STR, "line2": _STR}},
            "lines": {"type": "array", "items": {
                "type": "object", "required": ["text", "say", "keywords", "visual"],
                "properties": {"text": _STR, "say": _STR, "visual": _STR,
                               "keywords": {"type": "array", "items": _STR}}}},
            "images": {"type": "array", "items": {
                "type": "object", "required": ["key", "role", "subject", "prompt"],
                "properties": {"key": _STR, "role": {"type": "string", "enum": ["sticker", "background", "diagram"]},
                               "subject": _STR, "prompt": _STR}}},
        }}}},
}


def system_prompt(path=PROMPT) -> str:
    c = config.load()["shorts"]
    return (path.read_text(encoding="utf-8")
            .replace("{LINES_MIN}", str(c["lines_min"])).replace("{LINES_MAX}", str(c["lines_max"]))
            .replace("{IMAGES_MIN}", str(c["images_min"])).replace("{IMAGES_MAX}", str(c["images_max"]))
            .replace("{SECONDS}", str(c["target_seconds"]))
            .replace("{SYLLABLES}", str(int(c["target_seconds"]) * 8)))


def run(job: Job, only=None, force: bool = False, **_) -> None:
    if not job.units:
        raise SystemExit("원고가 없습니다 — 「새 작업·원고」에서 원고를 넣어 주세요")
    if any(u.is_html for u in job.units):
        run_terms(job, only=only, force=force)
    units = [u for u in job.units if not u.is_html]
    if not units:
        return
    if only:
        want = {w.rsplit("-", 1)[0] if w.count("-") >= 2 else w for w in only}
        units = [u for u in units if u.prefix in want] or units
    model = config.load()["claude"]["script_model"]
    for u in units:
        if not u.source:
            log(f"  · {u.prefix} 는 아직 안전 개작본(02_rewrite)이 없어요 — 「0 안전 개작」을 먼저 해 주세요.")
            continue
        cache = config.read_json(u.script_dir / "_s1.json", {}) or {}
        have = [i for i in job.ids() if i.startswith(u.prefix + "-")]
        if have and cache.get("hash") == u.hash and not force:
            detail(f"s1: {u.prefix} 개작본 그대로 — 건너뜀 ({len(have)}편)")
            log(f"「{u.section or u.name}」 대본은 이미 있어요 ({len(have)}편).")
            continue
        log(f"「{u.section or u.name}」 개작본으로 쇼츠 대본을 쓰는 중이에요 (1~3분) …")
        from .s0_rewrite import load_sections
        secs = (load_sections(u) or {}).get("sections") or []
        head = f"[교과] {job.get('title', '')}\n[단원] {u.chapter} / {u.section}\n\n"
        if secs:        # 새 개작 형식 — 소제목 하나 = 쇼츠 한 편(분기 규칙 대신 이 목록을 따른다)
            body = "\n\n".join(f"{s['label']} {s.get('title', '')}\n" + "\n".join(s.get("paragraphs") or []) for s in secs)
            head += (f"[쇼츠 구성 — 아래 소제목 {len(secs)}개마다 정확히 한 편, 같은 순서로. 각 편은 그 소제목의 글만 재료로 쓴다]\n"
                     + "\n".join(f"{s['label']} {s.get('title', '')}" for s in secs) + "\n\n[원고]\n")
            res = claude_cli.structured(head + body, system_prompt(), SCHEMA, model=model)
            if len(res.get("shorts") or []) != len(secs):
                log(f"  편 수({len(res.get('shorts') or [])})가 소제목 수({len(secs)})와 달라 다시 맡겨요 …")
                res = claude_cli.structured(head + body + f"\n\n[주의] shorts 는 정확히 {len(secs)}개.",
                                            system_prompt(), SCHEMA, model=model)
        else:           # 예전 개작본(소제목 구조 없음) — 분기 규칙대로
            res = claude_cli.structured(head + "[원고]\n" + u.text, system_prompt(), SCHEMA, model=model)
        shorts: List[Dict[str, Any]] = res.get("shorts") or []
        if not shorts:
            raise SystemExit("대본이 비어서 왔어요. 같은 버튼을 한 번 더 눌러 주세요.")
        for old in have:            # 편 수가 줄었을 수 있다 — 이전 대본 파일은 치운다(사람 수정 .edit.json 은 남긴다)
            (u.script_dir / f"{old}.json").unlink(missing_ok=True)
        for n, sh in enumerate(shorts, 1):
            sid = f"{u.prefix}-{n:02d}"
            sec_no = u.prefix.split("-")[1]
            title = (res.get("unit_title") or "").strip() or re.sub(r"^\d+절\s*", "", u.section)
            ch = u.chapter if len(u.chapter) > 3 else f"{u.prefix.split('-')[0]}장"
            sh = {"id": sid, "unit": f"{ch} {sec_no}절 {title}".strip(), "unit_topic": res.get("unit_topic", ""), **sh}
            if secs and n <= len(secs):
                sh["section"] = {"index": n, "label": secs[n - 1]["label"], "title": secs[n - 1].get("title", "")}
            for ln in sh.get("lines") or []:      # 자막에 없는 키워드는 강조가 안 된다 — 걸러 둔다
                ln["keywords"] = [k for k in ln.get("keywords") or [] if k and k in ln.get("text", "")]
            for i, im in enumerate(sh.get("images") or [], 1):
                im["key"] = im.get("key") or f"img{i}"
            config.write_json(u.script_dir / f"{sid}.json", sh)
            log(f"  ✓ {sid} {sh['perspective']} — {sh['hook']['line1']} (문장 {len(sh['lines'])} · 그림 {len(sh['images'])})")
        log(f"  이 절의 학습 주제: {res.get('unit_topic', '')}")
        config.write_json(u.script_dir / "_s1.json", {"hash": u.hash, "source": u.source.name})
        from . import ytmeta     # 대본 다음 바로 유튜브 업로드 문구(제목·해시태그·설명·태그·고정 댓글)
        ytmeta.write_unit(job, u, [f"{u.prefix}-{n:02d}" for n in range(1, len(shorts) + 1)], model=model)


# ── 용어 모드(HTML 원고) ──────────────────────────────────────────────────────
_TERM_ITEM = json.loads(json.dumps(SCHEMA["properties"]["shorts"]["items"]))
_TERM_ITEM["required"] = ["term"] + _TERM_ITEM["required"] + ["quiz"]
_TERM_ITEM["properties"]["term"] = _STR
_TERM_ITEM["properties"]["quiz"] = {"type": "object", "required": ["question", "answer", "explain"],
                                    "properties": {"question": _STR, "answer": _STR, "explain": _STR}}
_TERM_ITEM["properties"]["images"]["items"]["properties"]["role"]["enum"] = ["chart", "sticker", "background", "diagram"]
TERM_SCHEMA: Dict[str, Any] = {"type": "object", "required": ["shorts"],
                               "properties": {"shorts": {"type": "array", "minItems": 1, "items": _TERM_ITEM}}}


def _term_brief(job: Job, u, doc: Dict[str, Any], batch: List[Dict[str, Any]]) -> str:
    src = {s["id"]: s for s in doc["sources"]}
    out = [f"[시리즈] {job.get('title', '')}", f"[과목] {doc['title']}", f"[장] {u.section}", "",
           f"[이번에 쓸 용어 {len(batch)}개 — 이 순서로 한 편씩]"] + [f"{n}. {t['name']}" for n, t in enumerate(batch, 1)]
    for n, t in enumerate(batch, 1):
        out += ["", f"## {n}. 용어: {t['name']}",
                "[도식 재료] " + (f"있음 ({t.get('diagram_type')}) — role=chart 그림 1장을 넣을 것" if (t.get("mermaid") or "").strip() else "없음")]
        for sid in t["sources"]:
            s = src.get(sid)
            if not s:
                continue
            out += [f"[원고 소주제] {s['title']}", s["text"]]
            say = (s.get("metadata") or {}).get("data-say")
            if say:
                out += ["[같은 소주제의 강의 낭독 원고 — 설명 흐름 참고용]", say]
    return "\n".join(out)


def _term_key(t: Dict[str, Any], doc: Dict[str, Any], system: str) -> str:
    import hashlib
    src = {s["id"]: s["text"] for s in doc["sources"]}
    raw = json.dumps([t["name"], t.get("mermaid", ""), [src.get(s, "") for s in t["sources"]]], ensure_ascii=False)   # 프롬프트를 고쳐도 기존 대본은 유지(다시 쓰려면 --force)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def run_terms(job: Job, only=None, force: bool = False) -> None:
    from . import terms as terms_mod
    model = config.load()["claude"]["script_model"]
    system = system_prompt(TERM_PROMPT).replace("{EXAM}", job.get("exam") or job.get("title") or "SQLD")
    for u in [u for u in job.units if u.is_html]:
        tl = [t for t in terms_mod.load(u).get("terms") or [] if not t.get("skip")]     # 대시보드에서 「제외」한 용어는 안 만든다
        if only:
            tl = [t for t in tl if any(t["sid"] == w or u.prefix == w or u.prefix.split("-")[0] == w for w in only)]
        if not tl:
            if not only and not terms_mod.load(u):
                log(f"  · {u.prefix} 는 아직 용어 목록이 없어요 — 「0 용어 뽑기」를 먼저 해 주세요.")
            continue
        doc = u.doc()
        cache = config.read_json(u.script_dir / "_s1.json", {}) or {}
        keys = cache.get("terms") or {}
        todo = [t for t in tl if force or keys.get(t["sid"]) != _term_key(t, doc, system)
                or not (u.script_dir / f"{t['sid']}.json").exists()]
        if not todo:
            log(f"「{u.section}」 대본은 이미 있어요 ({len(tl)}편).")
            continue
        log(f"「{u.section}」 용어 {len(todo)}개의 쇼츠 대본을 쓰는 중이에요 ({TERM_BATCH}개씩, 묶음마다 1~3분) …")
        written: List[str] = []
        for off in range(0, len(todo), TERM_BATCH):
            batch = todo[off:off + TERM_BATCH]
            prompt = _term_brief(job, u, doc, batch)
            res = claude_cli.structured(prompt, system, TERM_SCHEMA, model=model)
            got = res.get("shorts") or []
            if len(got) != len(batch):
                log(f"  편 수({len(got)})가 용어 수({len(batch)})와 달라 다시 맡겨요 …")
                res = claude_cli.structured(prompt + f"\n\n[주의] shorts 는 정확히 {len(batch)}개, 용어 순서대로.",
                                            system, TERM_SCHEMA, model=model)
                got = res.get("shorts") or []
            for t, sh in zip(batch, got):
                sid = t["sid"]
                sh = {"id": sid, "unit": f"{doc['title']} · {u.section}", "unit_topic": t["name"],
                      **sh, "perspective": t["name"], "term": {"name": t["name"], "sources": t["sources"]}}
                for ln in sh.get("lines") or []:
                    ln["keywords"] = [k for k in ln.get("keywords") or [] if k and k in ln.get("text", "")]
                for i, im in enumerate(sh.get("images") or [], 1):
                    im["key"] = im.get("key") or f"img{i}"
                if not (t.get("mermaid") or "").strip():      # 도식 재료가 없으면 chart 는 일반 도해로
                    for im in sh.get("images") or []:
                        if im.get("role") == "chart":
                            im["role"] = "diagram"
                config.write_json(u.script_dir / f"{sid}.json", sh)
                keys[sid] = _term_key(t, doc, system)
                written.append(sid)
                log(f"  ✓ {sid} {t['name']} — {sh['hook']['line1']} (문장 {len(sh['lines'])} · 그림 {len(sh['images'])})")
            config.write_json(u.script_dir / "_s1.json", {"terms": keys, "source": u.raw.name})
        from . import ytmeta
        ytmeta.write_unit(job, u, written, model=model)
