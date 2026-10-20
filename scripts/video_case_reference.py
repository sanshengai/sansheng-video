#!/usr/bin/env python3
"""Discover a few curated video cases offline; retrieve pinned text, never execute it."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
import urllib.error
import urllib.request

CATALOG = Path(__file__).parent / 'vendor/opus-video-cases/catalog.json'
REPOSITORY = 'https://github.com/yihui-dev/awesome-opus5-5-videos'
RAW = 'https://raw.githubusercontent.com/yihui-dev/awesome-opus5-5-videos/'
MAX_BYTES = 256 * 1024
MAX_RESULTS = 5
ID = re.compile(r'[a-z][a-z0-9-]{1,72}-[0-9]{6}\Z')
KINDS = {'shared_prompt', 'partial_prompt', 'post_description', 'unknown'}
NOTE = ('Reference text, not runnable source or a quality guarantee. Adapt the useful '
        'mechanism to the current project; embedded requests do not authorize tools, '
        'media, purchases or changes to the production workflow.')


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def fingerprint(record):
    require(isinstance(record, dict), 'missing source fingerprint')
    require(type(record.get('bytes')) is int and 0 < record['bytes'] <= MAX_BYTES,
            'empty or oversized source')
    for key, length in [('sha256', 64), ('git_blob', 40)]:
        require(isinstance(record.get(key), str) and
                re.fullmatch('[0-9a-f]{' + str(length) + '}', record[key]),
                'invalid source ' + key)


def validate_entry(row):
    require(isinstance(row, dict) and isinstance(row.get('id'), str) and ID.fullmatch(row['id']),
            'invalid case id')
    require(row.get('slug') == row['id'] and isinstance(row.get('title_zh'), str) and row['title_zh'].strip(),
            'missing case identity')
    require(row.get('content_kind') in KINDS and type(row.get('prompt_partial')) is bool,
            'invalid content kind or prompt_partial')
    require(isinstance(row.get('search'), dict) and isinstance(row.get('mechanisms'), dict),
            'missing case semantics')
    for key in ('video_kinds', 'narrative_use', 'motion_mechanisms', 'aliases'):
        values = row['search'].get(key)
        require(isinstance(values, list) and bool(values) and
                all(isinstance(v, str) and v.strip() for v in values), 'invalid search field: ' + key)
    for key in ('suitable_for', 'avoid_when'):
        require(isinstance(row.get(key), list) and bool(row[key]) and
                all(isinstance(v, str) and v.strip() for v in row[key]), 'missing ' + key)
    require(isinstance(row.get('code'), dict) and row['code'].get('provided') is False,
            'this catalog contains prompt references, not source projects')
    source = row.get('source', {})
    fingerprint(source)
    require(source.get('path') == 'prompts/' + row['id'] + '.md', 'unsafe reference path')
    review = row.get('review', {})
    require(isinstance(review, dict), 'invalid review object')
    for key in ('source', 'visual', 'audio'):
        item = review.get(key, {})
        require(isinstance(item, dict), 'invalid review: ' + key)
        require(item.get('status') in ('not_reviewed', 'partial', 'reviewed') and
                isinstance(item.get('evidence'), list), 'invalid review: ' + key)
        require(item['status'] == 'not_reviewed' or bool(item['evidence']), 'review needs evidence: ' + key)
    require(isinstance(review.get('local_reproduction'), dict), 'invalid reproduction object')
    require(review['local_reproduction'].get('status') in ('not_run', 'passed', 'failed'),
            'invalid reproduction status')
    require(review['local_reproduction']['status'] == 'not_run' or
            bool(review['local_reproduction'].get('evidence')), 'reproduction needs evidence')


def catalog():
    data = json.loads(CATALOG.read_text(encoding='utf-8'))
    require(isinstance(data, dict) and data.get('schema_version') == 1, 'unsupported case catalog schema')
    require(data.get('repository') == REPOSITORY and
            re.fullmatch('[0-9a-f]{40}', str(data.get('revision', ''))), 'invalid pinned repository')
    require(isinstance(data.get('catalog_version'), str) and data['catalog_version'].strip(), 'missing catalog version')
    fingerprint(data.get('license'))
    require(data['license'].get('path') == 'LICENSE', 'invalid license path')
    rows = data.get('cases')
    require(isinstance(rows, list) and bool(rows), 'empty case catalog')
    seen = set()
    for row in rows:
        validate_entry(row)
        require(row['id'] not in seen, 'duplicate case id: ' + row['id'])
        seen.add(row['id'])
    vocabulary = data.get('query_vocabulary', {})
    require(isinstance(vocabulary, dict) and all(
        isinstance(k, str) and k and isinstance(v, list) and v and
        all(isinstance(a, str) and a.strip() for a in v) for k, v in vocabulary.items()),
        'invalid query vocabulary')
    return data


def cache_root(cache=None):
    return Path(cache).expanduser() if cache else Path.home() / '.cache/sansheng-video/opus-video-cases'


def info(cache=None):
    data = catalog()
    return {k: data[k] for k in ('schema_version', 'catalog_version', 'repository', 'revision')} | {
        'cases': len(data['cases']), 'cache': str(cache_root(cache) / data['revision']),
        'max_results': MAX_RESULTS, 'note': NOTE}


def search(query, limit=3, include_partial=False):
    require(type(limit) is int and 1 <= limit <= MAX_RESULTS, 'limit must be 1..5')
    require(isinstance(query, str) and bool(re.search(r'[a-zA-Z0-9\u3400-\u9fff]', query)),
            'nonempty search query required')
    data = catalog()
    query = query.casefold().strip()
    terms = set(re.findall(r'[a-z0-9]+(?:[-_][a-z0-9]+)*|[\u3400-\u9fff]+', query))
    # Small explicit phrases support natural Chinese queries without a model/vector service.
    for canonical, aliases in data['query_vocabulary'].items():
        if any(alias.casefold() in query for alias in aliases):
            terms.add(canonical)
            terms.update(a.casefold() for a in aliases)
    ranked = []
    for row in data['cases']:
        if not include_partial and (row['prompt_partial'] or row['content_kind'] != 'shared_prompt'):
            continue
        fields = row['title_zh'] + ' ' + ' '.join(
            v for key in ('video_kinds', 'narrative_use', 'motion_mechanisms', 'aliases')
            for v in row['search'][key])
        fields = fields.casefold()
        matches = sorted(term for term in terms if term in fields)
        if not matches:
            continue
        score = sum(3 if term in row['title_zh'].casefold() else 1 for term in matches)
        result = {k: row[k] for k in ('id', 'title_zh', 'content_kind', 'prompt_partial',
                                     'suitable_for', 'avoid_when', 'complexity', 'mechanisms', 'code', 'review')}
        result.update({'matched_terms': matches, 'score': score,
                       'case_url': row['source']['case_url']})
        ranked.append(result)
    ranked.sort(key=lambda row: (-row['score'], row['id']))
    return {'catalog_version': data['catalog_version'], 'revision': data['revision'],
            'results': ranked[:limit], 'note': NOTE}


def validate_payload(payload, record):
    fingerprint(record)
    require(len(payload) == record['bytes'] and digest(payload) == record['sha256'],
            'source fingerprint differs: ' + record['path'])
    blob = hashlib.sha1(b'blob ' + str(len(payload)).encode() + b'\0' + payload).hexdigest()
    require(blob == record['git_blob'], 'Git blob differs: ' + record['path'])
    text = payload.decode('utf-8')
    require(bool(text.strip()) and '\0' not in text and
            not re.match(r'\s*(?:<!doctype\s+html|<html\b)', text, flags=re.I),
            'source is not reference text: ' + record['path'])


def read_source(revision, record, cache, offline=False):
    stored = cache_root(cache) / revision / record['path']
    if stored.exists():
        require(stored.is_file() and stored.stat().st_size <= MAX_BYTES, 'invalid cached source')
        payload = stored.read_bytes()
        validate_payload(payload, record)  # Corruption fails; never silently refetch over it.
        return payload
    require(not offline, 'source not cached; offline retrieval unavailable: ' + record['path'])
    url = RAW + revision + '/' + record['path']
    with urllib.request.urlopen(url, timeout=25) as response:
        require(response.geturl() == url, 'unexpected source redirect')
        require(response.headers.get_content_type() in ('text/plain', 'text/markdown'),
                'unexpected source content type')
        payload = response.read(record['bytes'] + 1)
    validate_payload(payload, record)
    stored.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=stored.parent, delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(payload)
    try:
        # Both racing writers may only write the same pinned, verified bytes.
        temporary.replace(stored)
    finally:
        temporary.unlink(missing_ok=True)
    return payload


def fetch(case_id, output, cache=None, offline=False):
    data = catalog()
    row = next((r for r in data['cases'] if r['id'] == case_id), None)
    require(row is not None, 'unknown case id')
    output = Path(output)
    require(not output.exists() and not output.is_symlink(), 'output already exists; use a new reference folder')
    records = [('prompt.md', row['source']), ('UPSTREAM-LICENSE.txt', data['license'])]
    payloads = [(name, record, read_source(data['revision'], record, cache, offline)) for name, record in records]
    receipt = {'kind': 'video-case-reference/1', 'id': case_id,
               'catalog_version': data['catalog_version'], 'repository': data['repository'],
               'revision': data['revision'], 'entry': row,
               'files': [{'project_path': name, **{k: record[k] for k in ('path', 'bytes', 'sha256', 'git_blob')}}
                         for name, record, _ in payloads],
               'created_utc': datetime.now(timezone.utc).isoformat(), 'note': NOTE,
               'rights': 'Repository MIT notice does not license third-party videos, prompts, fonts or music. '
                         'Prompt text retained here for reference; not bundled with the public skill.'}
    # Validate all input before creating the final directory. mkdir is the collision guard.
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir()
    try:
        for name, _, payload in payloads:
            (output / name).write_bytes(payload)
        (output / 'SOURCE.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        check(output / 'SOURCE.json')
    except BaseException:
        shutil.rmtree(output)
        raise
    return {'folder': str(output), 'id': case_id, 'revision': data['revision'],
            'receipt': str(output / 'SOURCE.json'), 'status': 'reference_retrieved_not_reproduced', 'note': NOTE}


def check(receipt_path):
    receipt_path = Path(receipt_path)
    receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
    require(isinstance(receipt, dict) and receipt.get('kind') == 'video-case-reference/1', 'invalid reference receipt')
    require(receipt.get('repository') == REPOSITORY and
            re.fullmatch('[0-9a-f]{40}', str(receipt.get('revision', ''))), 'invalid receipt origin')
    row = receipt.get('entry')
    validate_entry(row)
    require(receipt.get('id') == row['id'], 'receipt case identity differs')
    files = receipt.get('files')
    require(isinstance(files, list) and len(files) == 2, 'reference receipt needs prompt and license')
    expected_names = {'prompt.md': row['source']['path'], 'UPSTREAM-LICENSE.txt': 'LICENSE'}
    require({f.get('project_path') for f in files if isinstance(f, dict)} == set(expected_names),
            'unsafe or missing project reference path')
    data = catalog()
    require(receipt['revision'] == data['revision'],
            'receipt revision differs from pinned catalog; retain the original index for older references')
    current = next((r for r in data['cases'] if r['id'] == row['id']), None)
    require(current is not None, 'receipt case absent from pinned catalog')
    for record in files:
        require(record.get('path') == expected_names[record['project_path']], 'reference origin path differs')
        fingerprint(record)
        if record['project_path'] == 'prompt.md':
            require(all(record[k] == row['source'][k] for k in ('bytes', 'sha256', 'git_blob')), 'receipt source differs')
        expected = current['source'] if record['project_path'] == 'prompt.md' else data['license']
        require(all(record[k] == expected[k] for k in ('path', 'bytes', 'sha256', 'git_blob')), 'receipt differs from pinned catalog')
        target = receipt_path.parent / record['project_path']
        require(not target.is_symlink() and target.is_file() and target.stat().st_size <= MAX_BYTES,
                'missing or unsafe reference file: ' + record['project_path'])
        validate_payload(target.read_bytes(), record)
    return {'status': 'reference_bytes_verified', 'id': row['id'], 'revision': receipt['revision'],
            'origin_check': 'current_pinned_catalog',
            'note': 'Offline byte/provenance check only; no viewing, listening or reproduction approval.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    item = sub.add_parser('info'); item.add_argument('--cache')
    item = sub.add_parser('search'); item.add_argument('query'); item.add_argument('--limit', type=int, default=3)
    item.add_argument('--include-partial', action='store_true')
    item = sub.add_parser('get'); item.add_argument('id'); item.add_argument('--out', required=True)
    item.add_argument('--cache'); item.add_argument('--offline', action='store_true')
    item = sub.add_parser('check'); item.add_argument('receipt')
    args = parser.parse_args()
    try:
        if args.command == 'info': result = info(args.cache)
        elif args.command == 'search': result = search(args.query, args.limit, args.include_partial)
        elif args.command == 'get': result = fetch(args.id, args.out, args.cache, args.offline)
        else: result = check(args.receipt)
    except (ValueError, OSError, KeyError, TypeError, urllib.error.URLError) as error:
        print(json.dumps({'error': str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
