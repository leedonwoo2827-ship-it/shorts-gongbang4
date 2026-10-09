"""HTML 원고(h1 문서 · h2 장 · h3 소주제) 읽기 — termbook-studio backend/parser.py 에서 가져왔다.

원고 마크업은 실행하지 않는다(스크립트·이벤트·외부 참조 제거). 원고 SVG 는 그대로 보존한다.
쇼츠공방4 추가: split_chapters() — h2 장마다 조각 HTML 로 나눠 단원 폴더에 넣는다.
"""
import re
import hashlib
from bs4 import BeautifulSoup, Tag

HTML_TAGS = set('p div span b strong i em u s sub sup ul ol li table thead tbody tfoot tr th td caption blockquote br hr details summary label input code pre h4 h5 a'.split())
SVG_TAGS = set('svg g defs marker path rect circle ellipse line polyline polygon text tspan title desc clippath lineargradient radialgradient stop'.split())
ATTRS = set('id class title colspan rowspan type checked viewbox xmlns x y dx dy x1 y1 x2 y2 cx cy r rx ry width height d points fill fill-rule stroke stroke-width stroke-linecap stroke-linejoin stroke-dasharray opacity fill-opacity stroke-opacity transform font-family font-size font-weight font-style letter-spacing text-anchor textlength lengthadjust dominant-baseline marker-end marker-start marker-mid markerwidth markerheight markerunits paint-order refx refy orient preserveaspectratio offset stop-color clip-path role aria-label aria-labelledby'.split())

def sanitize(markup, prefix):
    soup = BeautifulSoup(markup, 'html.parser')
    for tag in list(soup.find_all(True)):
        if tag.name is None:
            continue
        if tag.name.lower() not in HTML_TAGS | SVG_TAGS:
            tag.decompose()
            continue
        for key in list(tag.attrs):
            value = str(tag.attrs[key])
            if key.lower() not in ATTRS and not key.startswith('data-'):
                del tag.attrs[key]
            elif re.search(r'url\((?!#[\w-]+\))|javascript:|https?://', value, re.I) and key != 'xmlns':
                del tag.attrs[key]
        if tag.name == 'input':
            tag.attrs = {'type': 'checkbox', **({'checked': ''} if tag.has_attr('checked') else {})}
    ids = {t['id']: prefix + '-' + t['id'] for t in soup.select('[id]')}
    for t in soup.find_all(True):
        for k, v in list(t.attrs.items()):
            if isinstance(v, str):
                if k == 'id':
                    t[k] = ids[v]
                elif k == 'aria-labelledby':
                    t[k] = ' '.join(ids.get(s, s) for s in v.split())
                else:
                    for old, new in ids.items():
                        v = v.replace('url(#' + old + ')', 'url(#' + new + ')')
                    t[k] = v
    # HTML parsers lowercase SVG attributes. Restore their XML spellings.
    names = {'viewbox': 'viewBox', 'markerwidth': 'markerWidth', 'markerheight': 'markerHeight', 'refx': 'refX', 'refy': 'refY', 'preserveaspectratio': 'preserveAspectRatio', 'markerunits': 'markerUnits', 'textlength': 'textLength', 'lengthadjust': 'lengthAdjust'}
    for i, svg in enumerate(soup.find_all('svg')):
        for t in [svg, *svg.find_all(True)]:
            t.name = {'clippath': 'clipPath', 'lineargradient': 'linearGradient', 'radialgradient': 'radialGradient'}.get(t.name, t.name)
            for lower, camel in names.items():
                if lower in t.attrs:
                    t[camel] = t.attrs.pop(lower)
        title = svg.find('title', recursive=False)
        description = svg.find('desc', recursive=False)
        if not title:
            title = soup.new_tag('title')
            title.string = svg.get('aria-label', '원본 도식')
        else:
            title.extract()
        svg.insert(0, title)
        if not description:
            description = soup.new_tag('desc')
            description.string = svg.get('aria-label') or svg.get_text(' ', strip=True) or '원문에 포함된 도식'
            svg.insert(1, description)
        title['id'], description['id'] = f'{prefix}-svg-{i}-title', f'{prefix}-svg-{i}-desc'
        svg['role'] = 'img'
        svg['aria-labelledby'] = title['id'] + ' ' + description['id']
    return str(soup)

def plain(markup):
    return BeautifulSoup(markup, 'html.parser').get_text(' ', strip=True)

def term_id(name):
    return 't-' + hashlib.sha256(re.sub(r'\s+', '', name).casefold().encode()).hexdigest()[:16]

def seed_names(title):
    title = re.sub(r'^\d+(?:\.\d+)*\.?\s*', '', title)
    # Conservative offline seed; AI extraction handles semantic compounds later.
    if re.fullmatch(r'[A-Z][A-Z0-9-]*와\s*[A-Z][A-Z0-9-]*', title):
        return re.split(r'와\s*', title)
    return [title]

def rebuild_terms(doc):
    terms = {}
    for source in doc['sources']:
        for name in source['terms']:
            key = term_id(name)
            if key not in terms:
                terms[key] = {'id': key, 'name': name, 'source_ids': [], 'chapter_id': source['chapter_id']}
            if source['id'] not in terms[key]['source_ids']:
                terms[key]['source_ids'].append(source['id'])
    doc['terms'] = list(terms.values())

def parse_document(html, filename):
    soup = BeautifulSoup(html, 'html.parser')
    h1 = soup.find('h1')
    if not h1 or not soup.find('h2') or not soup.find('h3'):
        raise ValueError('필수 제목 구조가 없습니다. 문서 제목 h1, 장 h2, 소주제 h3가 필요합니다.')
    doc = {'title': h1.get_text(' ', strip=True), 'filename': filename, 'narration': {k: v for k, v in h1.attrs.items() if k.startswith('data-')}, 'chapters': [], 'sources': [], 'terms': [], 'status': 'ready', 'error': '', 'warnings': [], 'agent': ''}
    chapter = None
    seen = set()
    for heading in soup.find_all(['h2', 'h3']):
        if heading.name == 'h2':
            chapter = {'id': f'c-{len(doc["chapters"])+1}', 'title': heading.get_text(' ', strip=True)}
            doc['chapters'].append(chapter)
            continue
        if chapter is None:
            raise ValueError('첫 소주제 h3 앞에 장 제목 h2가 필요합니다.')
        source_id = heading.get('data-id') or f's-{len(doc["sources"])+1}'
        if source_id in seen:
            raise ValueError(f'중복 data-id: {source_id}')
        seen.add(source_id)
        title_soup = BeautifulSoup(str(heading), 'html.parser')
        for badge in title_soup.select('label, .q'):
            badge.decompose()
        title = title_soup.get_text(' ', strip=True)
        chunks = []
        for sibling in heading.next_siblings:
            if isinstance(sibling, Tag) and sibling.name in ('h1', 'h2', 'h3'):
                break
            chunks.append(str(sibling))
        markup = sanitize(''.join(chunks), f'src-{len(doc["sources"])}')
        body = BeautifulSoup(markup, 'html.parser')
        svgs = [str(svg) for svg in body.find_all('svg')]
        for svg in body.find_all('svg'):
            svg.decompose()
        doc['sources'].append({'id': source_id, 'chapter_id': chapter['id'], 'title': title, 'body': str(body), 'text': body.get_text(' ', strip=True), 'svgs': svgs, 'badge': sanitize(''.join(str(b) for b in heading.select('label.q')), f'badge-{len(doc["sources"])}'), 'metadata': {k: v for k, v in heading.attrs.items() if k.startswith('data-')}, 'terms': seed_names(title), 'status': 'pending', 'error': '', 'diagrams': [], 'mermaid': '', 'ledger': ''})
    doc['counts'] = {'chapters': len(doc['chapters']), 'sources': len(doc['sources']), 'svgs': sum(len(s['svgs']) for s in doc['sources'])}
    rebuild_terms(doc)
    return doc


def split_chapters(html):
    """원고 하나 → [(장 번호, 장 제목, 조각 HTML)]. 조각 = h1(문서 제목) + 그 장의 h2 와 내용. <style> 은 남겨 원문 모양을 보존."""
    soup = BeautifulSoup(html, 'html.parser')
    h1 = soup.find('h1')
    if not h1 or not soup.find('h2') or not soup.find('h3'):
        raise ValueError('필수 제목 구조가 없습니다. 문서 제목 h1, 장 h2, 소주제 h3가 필요합니다.')
    title = h1.get_text(' ', strip=True)
    styles = ''.join(str(s) for s in soup.find_all('style'))
    out = []
    for n, h2 in enumerate(soup.find_all('h2'), 1):
        chunks = [str(h2)]
        for sib in h2.next_siblings:
            if isinstance(sib, Tag) and (sib.name in ('h1', 'h2') or (sib.find('h2') is not None)):
                break
            chunks.append(str(sib))
        body = ''.join(chunks)
        page = ('<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>' + title + '</title>' + styles +
                '</head><body><h1>' + title + '</h1>' + body + '</body></html>')
        out.append((n, h2.get_text(' ', strip=True), page))
    return out
