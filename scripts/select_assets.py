#!/usr/bin/env python3
"""Bounded catalog contact sheets and source-checked project selections."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1048576), b''):
            result.update(chunk)
    return result.hexdigest()


def load_catalog(source):
    source = Path(source).resolve()
    data = json.loads(source.read_text())
    if data.get('kind') != 'sample-catalog/1':
        raise ValueError('expected sample-catalog/1')
    ids = [a['id'] for a in data['assets']]
    if len(set(ids)) != len(ids):
        raise ValueError('duplicate catalog identity')
    for path, expected in data.get('inputs', {}).items():
        if not Path(path).is_file() or digest(path) != expected:
            raise ValueError('catalog metadata missing or changed; export again: '+path)
    return source, data


def image_path(catalog, asset):
    if asset.get('kind') != 'image' or asset.get('availability') != 'available':
        raise ValueError('selection needs available image: ' + asset['id'])
    root = Path(catalog['roots'][asset['root']]).resolve()
    path = (root / asset['path']).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError('selected file missing or outside root: ' + asset['id'])
    if digest(path) != asset.get('sha256'):
        raise ValueError('selected file changed: ' + asset['id'])
    return path


def ratio(value):
    if isinstance(value, str):
        pieces = value.split(':')
        value = float(pieces[0]) / float(pieces[1]) if len(pieces) == 2 else float(value)
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise ValueError('invalid aspect ratio')
    return value


def sheet(source, output, purpose=None, aspect=None, group=None, limit=24):
    from PIL import Image, ImageOps, ImageDraw
    source, catalog = load_catalog(source)
    output = Path(output)
    if output.exists() or not 1 <= limit <= 48:
        raise ValueError('choose new sheet output and limit 1..48')
    members = None
    if group:
        groups = [g for g in catalog['groups'] if g['id'] == group]
        if len(groups) != 1:
            raise ValueError('unknown group')
        members = set(groups[0]['members'])
    target = ratio(aspect) if aspect else None
    candidates = []
    for asset in catalog['assets']:
        if asset.get('kind') != 'image' or asset.get('availability') != 'available':
            continue
        if members is not None and asset['id'] not in members:
            continue
        if purpose and purpose not in {asset.get('purpose'), asset.get('purpose_label')} and purpose not in (asset.get('topic') or ''):
            continue
        if target and (not asset.get('aspect') or abs(asset['aspect'] - target) / target >= .04):
            continue
        candidates.append(asset)
    if not candidates:
        raise ValueError('no matching available images; broaden filters or supply missing media')
    selected = candidates[:limit]
    columns = min(4, len(selected)); rows = math.ceil(len(selected) / columns)
    canvas = Image.new('RGB', (columns * 360, rows * 292), '#161819')
    draw = ImageDraw.Draw(canvas)
    listing = []
    for index, asset in enumerate(selected):
        path = image_path(catalog, asset)
        with Image.open(path) as original:
            image = ImageOps.contain(ImageOps.exif_transpose(original).convert('RGB'), (344, 236))
        x = index % columns * 360; y = index // columns * 292
        canvas.paste(image, (x + (360-image.width)//2, y + (244-image.height)//2))
        label = f"{index+1:02d} {asset.get('style', '?')} {asset.get('width')}x{asset.get('height')}"
        draw.text((x+8, y+246), label, fill='white')
        draw.text((x+8, y+265), str(asset.get('revision_state', 'unknown')), fill='#b0b8bc')
        listing.append({'number': index+1, 'id': asset['id'], 'sha256': asset['sha256'],
                        'purpose': asset.get('purpose'), 'topic': asset.get('topic'),
                        'revision_state': asset.get('revision_state'), 'rights': asset.get('rights')})
    output.parent.mkdir(parents=True, exist_ok=True)
    # A self-contained JSON sidecar maps printed numbers to complete stable IDs.
    sidecar = output.with_suffix(output.suffix + '.json')
    if sidecar.exists():
        raise ValueError('sheet sidecar already exists')
    canvas.save(output)
    sidecar.write_text(json.dumps({'kind': 'asset-contact-sheet/1', 'catalog': str(source),
                                  'catalog_sha256': digest(source), 'total_matches': len(candidates),
                                  'shown': listing, 'sheet_sha256': digest(output)}, ensure_ascii=False, indent=2)+'\n')
    return {'sheet': str(output), 'index': str(sidecar), 'shown': len(listing), 'matches': len(candidates)}


def lock(source, selection, output):
    from PIL import Image, ImageOps
    source, catalog = load_catalog(source)
    selection, output = Path(selection).resolve(), Path(output).resolve()
    if output.exists():
        raise ValueError('selection lock exists; choose new version')
    spec = json.loads(selection.read_text())
    if spec.get('kind') != 'asset-selection/1' or not isinstance(spec.get('items'), list) or not spec['items']:
        raise ValueError('expected nonempty asset-selection/1')
    canvas = spec.get('canvas')
    if not isinstance(canvas, list) or len(canvas) != 2 or any(type(v) is not int or not 64 <= v <= 4096 for v in canvas):
        raise ValueError('canvas needs two integers 64..4096')
    by_id = {a['id']: a for a in catalog['assets']}
    items, warnings, seen = [], [], set()
    inputs = {**catalog.get('inputs', {}), str(source): digest(source), str(selection): digest(selection)}
    for index, item in enumerate(spec['items']):
        ident = item['asset_id']
        if ident not in by_id:
            raise ValueError('unknown asset ID: ' + ident)
        asset = by_id[ident]; path = image_path(catalog, asset)
        fit = item.get('fit', 'contain'); focal = item.get('focal', [.5, .5])
        if fit not in {'contain', 'cover'} or not isinstance(focal, list) or len(focal) != 2 or any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1 for v in focal):
            raise ValueError('invalid fit/focal point')
        with Image.open(path) as original:
            image = ImageOps.exif_transpose(original)
            width, height = image.size
            image.load()
        factor = (min if fit == 'contain' else max)(canvas[0]/width, canvas[1]/height)
        if factor > 1.1:
            warnings.append({'item': index, 'reason': 'upscale', 'factor': round(factor, 3)})
        crop = 1 - min(width/height/(canvas[0]/canvas[1]), (canvas[0]/canvas[1])/(width/height))
        if fit == 'cover' and crop > .15:
            warnings.append({'item': index, 'reason': 'aspect_crop', 'fraction': round(crop, 3)})
        if ident in seen:
            warnings.append({'item': index, 'reason': 'repeated_asset', 'intent': item.get('repeat_reason')})
        seen.add(ident)
        if (asset.get('rights') or {}).get('sample_use', 'unknown') == 'unknown':
            warnings.append({'item': index, 'reason': 'unknown_use_rights'})
        if asset.get('revision_state') in {'historical', 'stale'}:
            warnings.append({'item': index, 'reason': 'revision_' + asset['revision_state']})
        if item.get('group'):
            groups = [g for g in catalog['groups'] if g['id'] == item['group'] and ident in g['members']]
            if len(groups) != 1:
                raise ValueError('item group not supported by catalog')
        items.append({**item, 'asset_id': ident, 'file': str(path), 'sha256': asset['sha256'],
                      'width': width, 'height': height, 'fit': fit, 'focal': focal,
                      'source': asset.get('source'), 'rights': asset.get('rights')})
        inputs[str(path)] = asset['sha256']
    for path, expected in inputs.items():
        if digest(path) != expected:
            raise ValueError('selection input changed while locking')
    result = {'kind': 'asset-selection-lock/1', 'canvas': canvas, 'items': items,
              'inputs': inputs, 'warnings': warnings, 'status': 'selected_not_reviewed'}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    return {'lock': str(output), 'items': len(items), 'warnings': warnings}


def verified(source):
    source = Path(source).resolve()
    data = json.loads(source.read_text())
    if data.get('kind') != 'asset-selection-lock/1' or not data.get('items') or not data.get('inputs'):
        raise ValueError('expected nonempty asset-selection-lock/1')
    for path, expected in data['inputs'].items():
        if not Path(path).is_file() or digest(path) != expected:
            raise ValueError('selection input missing or changed: ' + path)
    for item in data['items']:
        if data['inputs'].get(item['file']) != item['sha256']:
            raise ValueError('unbound selected asset')
    return data, {**data['inputs'], str(source): digest(source), str(Path(__file__).resolve()): digest(__file__)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sheets = sub.add_parser('sheet'); sheets.add_argument('catalog'); sheets.add_argument('output')
    for name in ('purpose', 'aspect', 'group'):
        sheets.add_argument('--'+name)
    sheets.add_argument('--limit', type=int, default=24)
    locks = sub.add_parser('lock'); locks.add_argument('catalog'); locks.add_argument('selection'); locks.add_argument('output')
    args = vars(parser.parse_args()); command = args.pop('command')
    if command == 'sheet':
        args['source'] = args.pop('catalog'); result = sheet(**args)
    else:
        result = lock(args['catalog'], args['selection'], args['output'])
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
