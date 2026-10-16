#!/usr/bin/env python3
"""Bounded Openverse search + chosen audio download. Does not approve rights/listening."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request

API = 'https://api.openverse.org/v1/audio/'
MAX_BYTES = 64 * 1024 * 1024


def read_url(url, limit=MAX_BYTES):
    if urllib.parse.urlsplit(url).scheme != 'https':
        raise ValueError('HTTPS URL required')
    req = urllib.request.Request(url, headers={'User-Agent': 'sansheng-video-audio/1.0'})
    with urllib.request.urlopen(req, timeout=15) as response:
        if urllib.parse.urlsplit(response.url).scheme != 'https':
            raise ValueError('HTTPS redirect required')
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError('response exceeds size limit')
    return data


def write_new(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(data)


def search(query, limit, cache):
    url = API + '?' + urllib.parse.urlencode({'q': query, 'license': 'cc0,by', 'page_size': limit})
    file = Path(cache) / (hashlib.sha256(url.encode()).hexdigest() + '.json')
    if file.exists() and time.time() - file.stat().st_mtime < 21600:
        return json.loads(file.read_text())
    try:
        data = json.loads(read_url(url, 4 * 1024 * 1024))
    except Exception as exc:
        raise ValueError(f'API search failed ({exc}). Open this URL in a browser; export its JSON and use fetch --record. No automatic retry: {url}') from exc
    if not isinstance(data.get('results'), list):
        raise ValueError('API response has no results list')
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(data, ensure_ascii=False))
    return data


def select(data, asset_id):
    rows = data.get('results', [data]) if isinstance(data, dict) else data
    if not isinstance(rows, list):
        raise ValueError('record must be one result, an array, or API results JSON')
    rows = [r for r in rows if isinstance(r, dict) and (not asset_id or r.get('id') == asset_id)]
    if len(rows) != 1:
        raise ValueError('select exactly one result with --id')
    record = rows[0]
    if record.get('license') not in ('cc0', 'by'):
        raise ValueError('default workflow accepts CC0 or CC BY; review other licenses separately')
    for key in ('id', 'url', 'foreign_landing_url', 'license_url', 'title', 'creator'):
        if not record.get(key):
            raise ValueError('missing record field: ' + key)
    return record


def fetch(record, output, cache):
    output = Path(output)
    receipt = output.with_name(output.name + '.source.json')
    if output.exists() or receipt.exists():
        raise ValueError('output or source receipt exists; choose a new path')
    blob = Path(cache) / (hashlib.sha256(record['url'].encode()).hexdigest() + '.audio')
    payload = blob.read_bytes() if blob.exists() else read_url(record['url'])
    if not payload or len(payload) > MAX_BYTES:
        raise ValueError('empty or oversized audio')
    with tempfile.NamedTemporaryFile(suffix=output.suffix) as tmp:
        tmp.write(payload); tmp.flush()
        probe = subprocess.run(['ffprobe', '-v', 'error', '-show_format', '-show_streams', '-of', 'json', tmp.name], capture_output=True, text=True)
        if probe.returncode:
            raise ValueError('download is not decodable media: ' + probe.stderr[-300:])
        info = json.loads(probe.stdout)
        if not any(s.get('codec_type') == 'audio' for s in info['streams']):
            raise ValueError('download has no audio stream')
        duration = float(info['format']['duration'])
        if not 0 < duration < float('inf'):
            raise ValueError('invalid audio duration')
    blob.parent.mkdir(parents=True, exist_ok=True)
    if not blob.exists():
        blob.write_bytes(payload)
    source = dict(record, retrieved_at=datetime.now(timezone.utc).isoformat(),
                  local_file=output.name, sha256=hashlib.sha256(payload).hexdigest(),
                  duration=duration, source_review='pending; tool checks metadata and media only',
                  listening_status='pending', attribution_status='pending' if record['license'] == 'by' else 'CC0; retain provenance')
    write_new(output, payload)
    write_new(receipt, (json.dumps(source, ensure_ascii=False, indent=2) + '\n').encode())
    return {'audio': str(output), 'source_receipt': str(receipt), 'sha256': source['sha256'], 'duration': duration}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', default=str(Path.home() / '.cache' / 'sansheng-video' / 'openverse'))
    sub = parser.add_subparsers(dest='command', required=True)
    find = sub.add_parser('search'); find.add_argument('query'); find.add_argument('--limit', type=int, choices=range(1, 6), default=3); find.add_argument('--out')
    get = sub.add_parser('fetch'); get.add_argument('--record', required=True); get.add_argument('--id'); get.add_argument('--output', required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'search':
            if not args.query.strip():
                raise ValueError('query must not be empty')
            data = search(args.query, args.limit, args.cache)
            if args.out:
                write_new(args.out, (json.dumps(data, ensure_ascii=False, indent=2) + '\n').encode())
                data = {'count': data.get('result_count'), 'candidates': [dict({k: r.get(k) for k in ('id', 'title', 'creator', 'license')}, duration_ms=r.get('duration')) for r in data['results']], 'record': args.out}
        else:
            record = select(json.loads(Path(args.record).read_text()), args.id)
            data = fetch(record, args.output, args.cache)
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
