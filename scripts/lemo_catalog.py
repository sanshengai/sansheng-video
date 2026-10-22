#!/usr/bin/env python3
"""Prepare a reviewable pinned reference update; never overwrite the live index."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import urllib.request

TEXT = {'.js', '.json', '.py', '.txt', '.md', '.mjs', '.sh', '.html', '.css'}
LIVE = Path(__file__).parent / 'vendor/lemo-opuscar'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def blob(raw):
    return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()


def prepare(source, revision, cards, tree, output, previous=LIVE):
    source, output = Path(source), Path(output)
    if not re.fullmatch('[0-9a-f]{40}', revision):
        raise ValueError('full immutable commit required')
    if output.exists():
        raise ValueError('candidate output already exists')
    if tree.get('truncated') or not tree.get('tree'):
        raise ValueError('complete nonempty upstream tree required')
    entries = {x['path']: x for x in tree['tree'] if x['type'] == 'blob'}

    def read(path):
        rel = Path(path)
        if rel.is_absolute() or '..' in rel.parts or path not in entries:
            raise ValueError('unbound source path: ' + path)
        target = source / rel
        if target.is_symlink() or not target.resolve().is_relative_to(source.resolve()):
            raise ValueError('unsafe source link: ' + path)
        raw = target.read_bytes()
        if blob(raw) != entries[path]['sha']:
            raise ValueError('source differs from upstream git blob: ' + path)
        return raw

    rows = json.loads(read('styleboard/catalog.json'))
    if not isinstance(rows, list) or not rows:
        raise ValueError('nonempty authoritative style catalog required')
    ids = [r.get('slug') for r in rows]
    if (any(not isinstance(s, str) or not re.fullmatch('[a-z0-9]+(?:-[a-z0-9]+)*', s)
            for s in ids) or len(set(ids)) != len(ids)):
        raise ValueError('invalid/duplicate style slug')
    index = json.loads(Path(cards).read_text())
    creative = index.get('styles', [])
    if (not creative or len({r['slug'] for r in creative}) != len(creative)
            or {r['slug'] for r in creative} != set(ids)):
        raise ValueError('reviewed card coverage differs from authoritative catalog')
    if not index.get('basis', '').strip():
        raise ValueError('honest research basis required')
    catalog = {'source': 'https://github.com/lemomo-ai/lemo-opuscar',
               'revision': revision, 'attribution': 'Lemomo / LemoLab, Lemo-Opuscar. Code/docs: MIT. Demo films/stills: CC BY 4.0 with attribution and modification notice. Excluded voice tracks and third-party materials require their own rights; read pinned README and CREDITS.',
               'styles': [], 'cinema': json.loads(read('styleboard/opuscar98_styles.json'))}
    payloads = {}
    for original in rows:
        row = dict(original)
        prefix = 'styles/' + row['slug'] + '/'
        paths = sorted(p for p in entries if p.startswith(prefix) and Path(p).suffix in TEXT)
        if prefix+'STYLE.md' not in paths or prefix+'DEMO.md' not in paths:
            raise ValueError('style lacks STYLE/DEMO: ' + row['slug'])
        files = []
        for path in paths:
            raw = read(path)
            raw.decode('utf-8')
            payloads[path] = raw
            files.append({'path': path, 'sha256': digest(raw), 'bytes': len(raw)})
        if sum(f['bytes'] for f in files) > 20*1024*1024:
            raise ValueError('style exceeds retrieval budget: ' + row['slug'])
        row['files'] = files
        catalog['styles'].append(row)
    bindings = {'schema': 'lemo-creative-sources/1', 'catalog_revision': revision,
                'research_revision': revision, 'files': {}}
    for card in creative:
        if (any(not isinstance(card.get(k), str) or not card[k].strip()
                for k in ('use_for', 'mechanism', 'visual', 'sound', 'needs', 'limits'))
                or not card.get('aliases') or not card.get('refs')):
            raise ValueError('incomplete reviewed card: ' + card['slug'])
        for ref in card['refs']:
            match = re.fullmatch(r'(styles/'+re.escape(card['slug'])+r'/[^\n]+):([1-9]\d*)', ref)
            if not match or match[1] not in payloads:
                raise ValueError('unbound reviewed reference: ' + ref)
            raw = payloads[match[1]]
            lines = len(raw.decode('utf-8').splitlines())
            if int(match[2]) > lines:
                raise ValueError('reference outside source: ' + ref)
            bindings['files'][match[1]] = {'sha256': digest(raw), 'lines': lines}
    index.update(catalog_revision=revision, research_revision=revision)
    index['compatibility'] = {'catalogued_text_files_compared': len(payloads), 'sha256_mismatches': 0}
    old = json.loads((previous/'catalog.json').read_text())
    oldfiles = {f['path']: f['sha256'] for r in old['styles'] for f in r['files']}
    newfiles = {p: digest(v) for p, v in payloads.items()}
    license_raw = read('LICENSE')
    # Include README in the git-verified review, because its media licensing may differ.
    readme_raw = read('README.md')
    report = {'revision': revision, 'previous_revision': old['revision'],
              'added_styles': sorted(set(ids)-{r['slug'] for r in old['styles']}),
              'removed_styles': sorted({r['slug'] for r in old['styles']}-set(ids)),
              'changed_text_files': sorted(p for p in oldfiles.keys() & newfiles.keys() if oldfiles[p]!=newfiles[p]),
              'added_text_files': sorted(newfiles.keys()-oldfiles.keys()),
              'removed_text_files': sorted(oldfiles.keys()-newfiles.keys()),
              'license_changed': license_raw != (previous/'LICENSE').read_bytes(),
              'readme_sha256': digest(readme_raw),
              'license_sha256': digest(license_raw),
              'style_count': len(ids), 'text_files': len(payloads),
              'status': 'candidate only; review source changes, citations and licensing before copying'}
    def encoded(d):
        return (json.dumps(d, ensure_ascii=False, indent=2)+'\n').encode()
    report['sources_sha256'] = digest(encoded(bindings))
    output.mkdir(parents=True)
    for name, data in [('catalog.json', catalog), ('creative-index.json', index),
                       ('creative-sources.json', bindings), ('review.json', report)]:
        (output/name).write_bytes(encoded(data))
    (output/'LICENSE').write_bytes(license_raw)
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', required=True, type=Path)
    p.add_argument('--revision', required=True)
    p.add_argument('--cards', required=True, type=Path)
    p.add_argument('--out', required=True, type=Path)
    a = p.parse_args()
    if not re.fullmatch('[0-9a-f]{40}', a.revision):
        p.error('full immutable commit required')
    url = 'https://api.github.com/repos/lemomo-ai/lemo-opuscar/git/trees/'+a.revision+'?recursive=1'
    request = urllib.request.Request(url, headers={'User-Agent': 'sansheng-video-reference-maintenance'})
    tree = json.load(urllib.request.urlopen(request, timeout=45))
    result = prepare(a.source, a.revision, a.cards, tree, a.out)
    print(json.dumps({k:v for k,v in result.items() if not k.endswith('_files')}, ensure_ascii=False, indent=2))
