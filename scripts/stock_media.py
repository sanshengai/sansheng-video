#!/usr/bin/env python3
"""Bounded Pexels video search and selected stock download, without a central library."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
from openverse_audio import write_new

LIMIT = 160 * 1024 * 1024
LICENSES = {'pexels': 'https://www.pexels.com/license/',
            'pixabay': 'https://pixabay.com/service/license-summary/'}


def read(url, limit, key=None):
    if urllib.parse.urlsplit(url).scheme != 'https':
        raise ValueError('HTTPS required')
    headers = {'User-Agent': 'sansheng-video-stock/1.0'}
    if key:
        headers['Authorization'] = key
    class Redirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, response_headers, newurl):
            if urllib.parse.urlsplit(newurl).scheme != 'https':
                raise ValueError('HTTPS redirect required')
            if key and urllib.parse.urlsplit(newurl).netloc != urllib.parse.urlsplit(url).netloc:
                raise ValueError('credential-bearing cross-origin redirect refused')
            return super().redirect_request(req, fp, code, msg, response_headers, newurl)
    opener = urllib.request.build_opener(Redirect())
    with opener.open(urllib.request.Request(url, headers=headers), timeout=25) as response:
        if urllib.parse.urlsplit(response.url).scheme != 'https':
            raise ValueError('HTTPS redirect required')
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError('response exceeds size limit')
    return data


def search(query, orientation, cache):
    if not query.strip():
        raise ValueError('query must not be empty')
    page = 'https://www.pexels.com/search/videos/' + urllib.parse.quote(query, safe='') + '/'
    key = os.environ.get('PEXELS_API_KEY')
    if not key:
        return {'status': 'browser_required', 'url': page,
                'reason': 'PEXELS_API_KEY is not configured; use the same source in browser, select at most 3 candidates'}
    url = 'https://api.pexels.com/videos/search?' + urllib.parse.urlencode(
        {'query': query, 'orientation': orientation, 'per_page': 3})
    file = Path(cache) / (hashlib.sha256(url.encode()).hexdigest() + '.json')
    if file.exists() and time.time() - file.stat().st_mtime < 21600:
        return json.loads(file.read_text())
    try:
        raw = json.loads(read(url, 4 * 1024 * 1024, key))
    except Exception:
        # Never stringify a credential-bearing request exception.
        return {'status': 'browser_required', 'url': page, 'reason': 'API unavailable; no retry or provider switch performed'}
    rows = []
    for video in raw['videos'][:3]:
        variants = [v for v in video.get('video_files', []) if v.get('file_type') == 'video/mp4' and v.get('width') and v.get('height')]
        if not variants:
            continue
        # Prefer <=1080p variants; avoid downloading 4K for a first look.
        suitable = [v for v in variants if min(v['width'], v['height']) <= 1080] or variants
        v = max(suitable, key=lambda v: min(v['width'], v['height']))
        rows.append({'provider': 'pexels', 'id': str(video['id']), 'page_url': video['url'],
                     'creator': video['user']['name'], 'license_url': LICENSES['pexels'],
                     'url': v['link'], 'width': v['width'], 'height': v['height'],
                     'duration': video['duration'], 'query': query})
    result = {'status': 'candidates', 'results': rows}
    file.parent.mkdir(parents=True, exist_ok=True); file.write_text(json.dumps(result))
    return result


def fetch(record, output):
    provider = record.get('provider')
    if provider not in LICENSES or record.get('license_url') != LICENSES[provider]:
        raise ValueError('provider and exact license URL required')
    for key in ('id', 'page_url', 'creator', 'url'):
        if not isinstance(record.get(key), str) or not record[key].strip():
            raise ValueError('missing record field: ' + key)
    domain = urllib.parse.urlsplit(record['page_url']).hostname or ''
    expected = 'pexels.com' if provider == 'pexels' else 'pixabay.com'
    if domain != expected and not domain.endswith('.' + expected):
        raise ValueError('source page does not belong to provider')
    output = Path(output); receipt = output.with_name(output.name + '.source.json')
    if output.exists() or receipt.exists():
        raise ValueError('output or source receipt exists; choose a new path')
    payload = read(record['url'], LIMIT)
    with tempfile.NamedTemporaryFile(suffix='.mp4') as tmp:
        tmp.write(payload); tmp.flush()
        p = subprocess.run(['ffprobe', '-v', 'error', '-show_format', '-show_streams', '-of', 'json', tmp.name], capture_output=True, text=True, timeout=30)
        if p.returncode:
            raise ValueError('download is not decodable video')
        info = json.loads(p.stdout)
        streams = [s for s in info['streams'] if s['codec_type'] == 'video']
        if not streams or not 0 < float(info['format']['duration']) < float('inf'):
            raise ValueError('download has no valid video stream')
    source = dict(record, sha256=hashlib.sha256(payload).hexdigest(),
                  retrieved_at=datetime.now(timezone.utc).isoformat(), local_file=output.name,
                  actual_duration=float(info['format']['duration']), actual_width=streams[0]['width'],
                  actual_height=streams[0]['height'], rights_review='pending', visual_review='pending',
                  audio_policy='inspect original audio; do not mix automatically')
    write_new(output, payload)
    write_new(receipt, (json.dumps(source, ensure_ascii=False, indent=2) + '\n').encode())
    return {'video': str(output), 'source_receipt': str(receipt), 'sha256': source['sha256']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', default=str(Path.home() / '.cache/sansheng-video/stock'))
    sub = parser.add_subparsers(dest='command', required=True)
    s = sub.add_parser('search'); s.add_argument('query'); s.add_argument('--orientation', choices=['landscape', 'portrait', 'square'], default='landscape'); s.add_argument('--out')
    f = sub.add_parser('fetch'); f.add_argument('--record', required=True); f.add_argument('--id'); f.add_argument('--output', required=True)
    args = parser.parse_args()
    if args.command == 'search':
        result = search(args.query, args.orientation, args.cache)
        if args.out:
            write_new(args.out, (json.dumps(result, ensure_ascii=False, indent=2) + '\n').encode())
    else:
        data = json.loads(Path(args.record).read_text())
        rows = data.get('results', [data]) if isinstance(data, dict) else data
        rows = [r for r in rows if not args.id or str(r.get('id')) == args.id]
        if len(rows) != 1:
            raise ValueError('select exactly one record with --id')
        result = fetch(rows[0], args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
