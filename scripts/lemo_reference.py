#!/usr/bin/env python3
"""Bounded, offline style discovery; fetch pinned reference text without executing it."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import urllib.request

CATALOG = Path(__file__).parent / 'vendor/lemo-opuscar/catalog.json'


def catalog():
    return json.loads(CATALOG.read_text())


def search(query, cinema=False):
    terms = re.findall(r'[a-z0-9_-]+|[\u3400-\u9fff]+', query.lower())
    if not terms:
        raise ValueError('nonempty search query required')
    data = catalog()
    rows = data['cinema']['films'] if cinema else data['styles']
    ranked = []
    for row in rows:
        fields = {k:v for k,v in row.items() if k not in ('files', 'shots', 'refs')}
        text = json.dumps(fields, ensure_ascii=False).lower()
        title = ' '.join(str(row.get(k,'')) for k in ('slug','en','cn','style_en','style_zh')).lower()
        score = sum((5 if term in title else 1) for term in terms if term in text)
        if score:
            ranked.append((score,fields))
    ranked.sort(key=lambda r: -r[0])
    return {'revision': data['revision'], 'kind': 'cinema-grammar' if cinema else 'style',
            'results': [r[1] for r in ranked[:3]], 'note': 'Reference only; no characters, demo story or facts are licensed by selection'}


def fetch(slug, output, demo=False, cache=None):
    data = catalog()
    row = next((r for r in data['styles'] if r['slug'] == slug), None)
    if row is None:
        raise ValueError('unknown style slug')
    output = Path(output)
    if output.exists():
        raise ValueError('output already exists; use a new reference folder')
    files = [f for f in row['files'] if demo or f['path'].endswith('/STYLE.md')]
    if not files or sum(f['bytes'] for f in files) > 20 * 1024 * 1024:
        raise ValueError('empty or oversized source selection')
    cache = Path(cache or Path.home()/'.cache/sansheng-video/lemo') / data['revision']
    # Validate every path/hash before any file is written.
    for f in files:
        rel = Path(f['path'])
        if rel.is_absolute() or '..' in rel.parts or not f['path'].startswith('styles/'+slug+'/'):
            raise ValueError('unsafe reference path')
    output.mkdir(parents=True)
    for f in files:
        stored = cache/f['path']
        payload = stored.read_bytes() if stored.exists() else urllib.request.urlopen(
            'https://raw.githubusercontent.com/lemomo-ai/lemo-opuscar/'+data['revision']+'/'+f['path'],timeout=25).read(f['bytes']+1)
        if len(payload) != f['bytes'] or hashlib.sha256(payload).hexdigest() != f['sha256']:
            raise ValueError('source fingerprint differs: '+f['path'])
        stored.parent.mkdir(parents=True,exist_ok=True);stored.write_bytes(payload)
        target = output/f['path'];target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(payload)
    (output/'LICENSE').write_bytes(CATALOG.with_name('LICENSE').read_bytes())
    receipt={'source':data['source'],'revision':data['revision'],'style':slug,'files':files,
             'attribution':data['attribution'],'demo_included':demo,
             'status':'reference text only; not executed, dependencies/media not installed; adapt selected mechanism into project'}
    (output/'SOURCE.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    return {'folder':str(output),'files':len(files),'revision':data['revision']}


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='command',required=True)
    q=s.add_parser('search');q.add_argument('query');q.add_argument('--cinema',action='store_true')
    g=s.add_parser('get');g.add_argument('slug');g.add_argument('--out',required=True);g.add_argument('--demo',action='store_true');g.add_argument('--cache')
    a=p.parse_args();result=search(a.query,a.cinema) if a.command=='search' else fetch(a.slug,a.out,a.demo,a.cache)
    print(json.dumps(result,ensure_ascii=False,indent=2))
