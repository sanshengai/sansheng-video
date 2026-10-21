#!/usr/bin/env python3
"""Render an exported project with explicit local runtime and stale checks.

A render receipt is technical evidence only, never human audiovisual approval.
This adapter currently uses the existing HyperFrames 0.8.72 / 30fps contract.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess

from runtime_support import locate_renderer, managed_command, verify_clip
from production_timeline import check, digest, encoded
from production_sound import preflight as sound_preflight
from production_sound_review import current_plan, pending, listening_page


def runtime_roots(runtime, browser):
    package, browser = Path(runtime).resolve(), Path(browser).resolve()
    if package.parent.name != 'node_modules':
        raise ValueError('runtime must be a locked package inside node_modules')
    browser_root = next((p for p in browser.parents if p.suffix == '.app'), None)
    if browser_root is None:
        if browser.name != 'chrome-headless-shell':
            raise ValueError('browser bundle boundary unknown; use verified Chromium app or headless shell')
        browser_root = browser.parent
    return [str(package.parent), str(browser_root)]


def inventory(roots):
    files = {}
    for root in map(Path, roots):
        if not root.is_dir():
            raise ValueError('runtime tree missing: ' + str(root))
        for path in sorted(root.rglob('*')):
            if path.is_symlink() and (not path.resolve().is_relative_to(root) or path.is_dir()):
                raise ValueError('runtime tree has unsupported symlink: ' + str(path))
            if path.is_file():
                files[str(path)] = digest(path)
        if not any(Path(name).is_relative_to(root) for name in files):
            raise ValueError('empty runtime tree: ' + str(root))
    return files


def runtime_files(runtime, browser):
    package = Path(runtime).resolve()
    files = inventory(runtime_roots(runtime, browser))
    fixed = [Path(__file__).resolve(), *[Path(__file__).with_name(name).resolve() for name in
             ('runtime_support.py', 'production_sound.py', 'production_sound_review.py', 'generate_sfx_tags.py')]]
    for name in ('node', 'ffmpeg', 'ffprobe'):
        binary = shutil.which(name)
        if not binary:
            raise ValueError('required local executable missing: ' + name)
        fixed.append(Path(binary).resolve())
    lock = package.parent.parent / 'package-lock.json'
    if lock.is_file():
        fixed.append(lock)
    files.update({str(path): digest(path) for path in fixed})
    return files


def verify(receipt_path):
    receipt_path = Path(receipt_path).resolve()
    receipt = json.loads(receipt_path.read_text())
    if receipt.get('kind') != 'production-render/1':
        raise ValueError('unknown render receipt')
    check(receipt['build_path'])
    if digest(receipt['build_path']) != receipt['build_sha256']:
        raise ValueError('render stale: production build changed')
    if receipt['host'] != {'system': platform.system(), 'release': platform.release(), 'machine': platform.machine()}:
        raise ValueError('render runtime host changed')
    if receipt.get('runtime_roots'):
        current_tree = inventory(receipt['runtime_roots'])
        saved_tree = {name: value for name, value in receipt['runtime_files'].items()
                      if any(Path(name).is_relative_to(root) for root in receipt['runtime_roots'])}
        if current_tree != saved_tree:
            raise ValueError('render runtime tree changed')
    for name, expected in receipt['runtime_files'].items():
        if not Path(name).is_file() or digest(name) != expected:
            raise ValueError('render runtime changed: ' + name)
    output = Path(receipt['output'])
    if not output.is_file() or digest(output) != receipt['output_sha256']:
        raise ValueError('render output changed or missing')
    build_data = json.loads(Path(receipt['build_path']).read_text())
    if 'source' in build_data or 'sound_review_plan_sha256' in receipt:
        _, plan_sha = current_plan(receipt['build_path'])
        if receipt.get('sound_review_plan_sha256') != plan_sha:
            raise ValueError('render sound review plan changed')
        declared_audio = receipt.get('verification', {}).get('has_audio')
        actual_audio = bool(json.loads(subprocess.run(
            ['ffprobe', '-v', 'error', '-select_streams', 'a', '-show_entries', 'stream=index',
             '-of', 'json', str(output)], capture_output=True, text=True, check=True).stdout)['streams'])
        if type(declared_audio) is not bool or declared_audio != actual_audio:
            raise ValueError('render audio presence evidence missing or differs from final movie')
    return {'status': 'current_not_reviewed', 'output': str(output)}


def check_review(project, output, review_path):
    """Consume the existing final-review file; never author human approval."""
    from review_binding import verify_production_review
    project, output, review_path = (Path(p).resolve() for p in (project, output, review_path))
    if not (project / 'derived/production-build.json').is_file():
        raise ValueError('production review requires current build evidence')
    review = json.loads(review_path.read_text())
    if not isinstance(review, dict):
        raise ValueError('final review must be an object')
    if not output.with_suffix('.render.json').is_file() and not review.get('render_receipt'):
        raise ValueError('production review requires render receipt')
    evidence = verify_production_review(project, output, review)
    return {'status': 'review_binding_current', 'output': str(output), 'evidence': evidence}


def prepare_review(project, output, review_path, *, refresh=False):
    """Prepare the audio section of the existing final review, always pending."""
    requested = Path(review_path).absolute()
    if requested.is_symlink():
        raise ValueError('review cannot be a symlink')
    project, output, review_path = (Path(p).resolve() for p in (project, output, review_path))
    if not output.is_relative_to(project) or not review_path.is_relative_to(project):
        raise ValueError('review and movie must be project-local')
    if review_path.suffix != '.json':
        raise ValueError('final review must use a JSON file')
    receipt_path = output.with_suffix('.render.json')
    verify(receipt_path)
    receipt = json.loads(receipt_path.read_text())
    if Path(receipt['output']).resolve() != output:
        raise ValueError('render receipt belongs to another movie')
    build = project / 'derived/production-build.json'
    if Path(receipt['build_path']).resolve() != build:
        raise ValueError('render receipt belongs to another production build')
    plan_data, plan_sha = current_plan(build)
    if receipt.get('sound_review_plan_sha256') != plan_sha:
        raise ValueError('legacy render needs current sound-plan evidence; re-export and render')
    page = review_path.with_suffix('.listen.html')
    protected = {output, receipt_path, build, *map(Path, json.loads(build.read_text())['inputs']),
                 *map(Path, receipt.get('runtime_files', {}))}
    if any(p in protected or p.is_relative_to(build.parent) or p.is_symlink() for p in (requested, review_path, page)):
        raise ValueError('review outputs would overwrite production evidence or dependencies')
    if (review_path.exists() or page.exists()) and not refresh:
        raise ValueError('review exists; use a new path or --refresh to reset pending')
    value = {'approved': False, 'output_sha256': digest(output),
             'production_build_sha256': digest(build), 'render_receipt_sha256': digest(receipt_path),
             'render_receipt': str(receipt_path.relative_to(project))}
    has_audio = receipt.get('verification', {}).get('has_audio')
    if type(has_audio) is not bool:
        raise ValueError('actual render audio presence evidence missing')
    if has_audio:
        value['audio_review'] = pending(plan_data, plan_sha, value['output_sha256'])
    review_path.parent.mkdir(parents=True, exist_ok=True)
    review_path.write_text(encoded(value))
    page.write_text(listening_page(output, page, plan_data))
    return {'status': 'pending_actual_review', 'review': str(review_path), 'listening_page': str(page),
            'listening_required': has_audio, 'windows': len(plan_data['items']) if has_audio else 0}


def render(project, source, runtime, browser, output, refresh=False, quality='draft'):
    if quality not in ('draft', 'standard', 'high'):
        raise ValueError('quality must be draft, standard or high')
    requested_output = Path(output).absolute()
    if requested_output.is_symlink():
        raise ValueError("render output path cannot contain symlinks")
    project, source, output = (Path(p).resolve() for p in (project, source, output))
    build = project / 'derived/production-build.json'
    check(build)
    metadata = json.loads(build.read_text())
    if str(source) not in metadata['inputs'] or str(project / 'index.html') not in metadata['inputs']:
        raise ValueError('source and index.html must be dependencies of this production build')
    data = json.loads(source.read_text())
    if data['fps'] != 30:
        raise ValueError('this renderer adapter currently validates 30fps only')
    if not output.is_relative_to(project) or output.suffix != '.mp4':
        raise ValueError('output must be a project-local MP4')
    if str(output) in metadata['inputs']:
        raise ValueError('render output would overwrite a source dependency')
    if output.is_symlink() or (output.exists() and not refresh):
        raise ValueError('output exists or is a symlink; use a new output or explicit --refresh')
    sound = sound_preflight(project, data, metadata)
    browser = Path(browser).resolve()
    if not browser.is_file():
        raise ValueError('explicit local browser missing; no automatic download')
    command = locate_renderer(runtime) + ['render', str(project), '--output', str(output), '--fps', '30',
                                         '--quality', quality, '--workers', '2', '--experimental-fast-capture=false']
    inputs = runtime_files(runtime, browser)
    build_hash = digest(build)
    output.parent.mkdir(parents=True, exist_ok=True)
    log = output.with_suffix('.render.log')
    env = {**os.environ, 'HYPERFRAMES_SKIP_SKILLS': '1', 'HYPERFRAMES_BROWSER_PATH': str(browser)}
    with log.open('w') as stream:
        result = subprocess.run(managed_command(command), env=env, stdout=stream, stderr=subprocess.STDOUT)
    if result.returncode:
        raise ValueError(f'render failed ({result.returncode}); see {log}')
    check(build)
    if digest(build) != build_hash or runtime_files(runtime, browser) != inputs:
        raise ValueError('inputs changed while rendering; output cannot be accepted')
    if sound_preflight(project, data, metadata) != sound:
        raise ValueError('sound wiring changed while rendering')
    probe = verify_clip(output, {'width': data['canvas'][0], 'height': data['canvas'][1], 'duration': data['duration']})
    streams = json.loads(subprocess.run(['ffprobe', '-v', 'error', '-show_streams', '-of', 'json', str(output)],
                                       capture_output=True, text=True, check=True).stdout)['streams']
    has_audio = any(s['codec_type'] == 'audio' for s in streams)
    if has_audio != data['requires_audio']:
        raise ValueError('render audio presence differs from declared intention')
    receipt = {'kind': 'production-render/1', 'status': 'rendered_not_reviewed', 'output': str(output),
               'output_sha256': digest(output), 'build_path': str(build), 'build_sha256': build_hash,
               'sound_review_plan_sha256': sound['review_plan_sha256'],
               'runtime_files': inputs, 'runtime_roots': runtime_roots(runtime, browser), 'host': {'system': platform.system(), 'release': platform.release(), 'machine': platform.machine()},
               'command': command, 'browser': str(browser), 'verification': {**probe, 'has_audio': has_audio,
                                                                             'sound_wiring': sound}}
    receipt_path = output.with_suffix('.render.json')
    receipt_path.write_text(encoded(receipt))
    return {'status': receipt['status'], 'receipt': str(receipt_path), 'output': str(output)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    build = subs.add_parser('render')
    for name in ('project', 'source', 'runtime', 'browser', 'output'):
        build.add_argument('--' + name, required=True, type=Path)
    build.add_argument('--refresh', action='store_true')
    build.add_argument('--quality', choices=('draft', 'standard', 'high'), default='draft')
    verify_parser = subs.add_parser('check')
    verify_parser.add_argument('receipt', type=Path)
    review_parser = subs.add_parser('check-review')
    for name in ('project', 'output', 'review'):
        review_parser.add_argument('--' + name, required=True, type=Path)
    prepare_parser = subs.add_parser('prepare-review')
    for name in ('project', 'output', 'review'):
        prepare_parser.add_argument('--' + name, required=True, type=Path)
    prepare_parser.add_argument('--refresh', action='store_true')
    args = parser.parse_args()
    if args.command == 'prepare-review':
        print(encoded(prepare_review(args.project, args.output, args.review, refresh=args.refresh)), end='')
        raise SystemExit(0)
    if args.command == 'check-review':
        print(encoded(check_review(args.project, args.output, args.review)), end='')
        raise SystemExit(0)
    result = (verify(args.receipt) if args.command == 'check' else
              render(args.project, args.source, args.runtime, args.browser, args.output, args.refresh, args.quality))
    print(encoded(result), end='')
