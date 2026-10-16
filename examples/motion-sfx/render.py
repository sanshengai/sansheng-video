#!/usr/bin/env python3
"""Rebuild the selected Canvas example and mix exported production cues. No HF claim."""
import argparse
import functools
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parent
SKILL = ROOT.parents[1]


def run(args):
    return subprocess.run(list(map(str, args)), check=True, capture_output=True, timeout=120).stdout


def digest(data):
    return hashlib.sha256(data).hexdigest()


def pcm(path):
    data = run(['ffmpeg', '-v', 'error', '-i', path, '-f', 'f32le', '-ar', '44100', '-ac', '1', '-'])
    return struct.unpack('<' + 'f' * (len(data)//4), data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve(); report = output.with_suffix('.validation.json')
    if output.exists() or report.exists():
        raise ValueError('use a new output name')
    from playwright.sync_api import sync_playwright
    with tempfile.TemporaryDirectory(prefix='motion-sfx-') as directory:
        work = Path(directory)
        for file in ('index.html', 'kit-lp.js', 'ripple.js', 'assets.lock.json', 'timeline.json'):
            shutil.copyfile(ROOT/file, work/file)
        shutil.copytree(ROOT/'assets', work/'assets')
        run([sys.executable, SKILL/'scripts/production_timeline.py', 'export', work/'timeline.json', work/'derived', '--dependency', work/'ripple.js', '--dependency', work/'kit-lp.js', '--dependency', work/'assets/click.wav', '--dependency', work/'assets.lock.json', '--dependency', work/'index.html'])
        run([sys.executable, SKILL/'scripts/production_timeline.py', 'check', work/'derived/production-build.json'])
        run([sys.executable, SKILL/'scripts/generate_sfx_tags.py', work/'index.html', '--manifest', work/'assets.lock.json', '--cues', work/'derived/sound-cues.json', '--apply'])
        timeline = json.loads((work/'timeline.json').read_text())
        cues = json.loads((work/'derived/sound-cues.json').read_text())
        class Quiet(SimpleHTTPRequestHandler):
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=str(work)))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        frames = work/'frames'; frames.mkdir()
        seek = {}
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                page = browser.new_page(viewport={'width':1280, 'height':720}, device_scale_factor=1)
                page.goto(f'http://127.0.0.1:{server.server_port}/index.html')
                page.wait_for_function('typeof window.renderFrame === "function"')
                page.evaluate('document.fonts.ready')
                def frame(t):
                    page.evaluate('t => window.renderFrame(t)', t)
                    return page.locator('canvas').screenshot()
                for t in (0, .7333333333, 1, 2.9333333333, 3.5):
                    first = digest(frame(t)); frame(4.7); reverse = digest(frame(t))
                    page.reload(); page.wait_for_function('typeof window.renderFrame === "function"'); page.evaluate('document.fonts.ready')
                    cold = digest(frame(t))
                    if not first == reverse == cold:
                        raise ValueError('seek mismatch at ' + str(t))
                    seek[str(t)] = first
                for i in range(round(timeline['duration']*timeline['fps'])):
                    (frames/f'{i:04d}.png').write_bytes(frame(i/timeline['fps']))
                browser.close()
        finally:
            server.shutdown(); server.server_close()
        run(['ffmpeg','-v','error','-framerate',str(timeline['fps']),'-i',frames/'%04d.png','-c:v','libx264','-pix_fmt','yuv420p',work/'silent.mp4'])
        filters = ['[2:a]asplit=' + str(len(cues)) + ''.join(f'[c{i}]' for i in range(len(cues)))]; labels = ['[1:a]']
        for i,cue in enumerate(cues):
            label = f's{i}'; labels.append(f'[{label}]')
            filters.append(f"[c{i}]atrim=duration={cue['duration']},asetpts=PTS-STARTPTS,volume={cue['volume']},adelay={cue['time']*1000}:all=1[{label}]")
        filters.append(''.join(labels)+f"amix=inputs={len(cues)+1}:normalize=0:duration=longest[a]")
        output.parent.mkdir(parents=True, exist_ok=True)
        run(['ffmpeg','-v','error','-i',work/'silent.mp4','-f','lavfi','-i',f"anullsrc=r=44100:cl=stereo:d={timeline['duration']}",'-i',work/'assets/click.wav','-filter_complex',';'.join(filters),'-map','0:v','-map','[a]','-c:v','copy','-c:a','aac','-b:a','320k','-movflags','+faststart','-t',str(timeline['duration']),output])
        run(['ffmpeg','-v','error','-i',output,'-f','null','-'])
        source = pcm(work/'assets/click.wav'); mixed = pcm(output)
        correlations = []
        for cue in cues:
            at = round(cue['time']*44100); segment = mixed[at:at+len(source)]
            energy = (sum(x*x for x in source)*sum(y*y for y in segment))**.5
            if energy == 0:
                raise ValueError('source or output is silent at a cue')
            score = sum(x*y for x,y in zip(source,segment)) / energy
            if score < .95:
                raise ValueError('audio missing or misaligned')
            correlations.append(score)
        result = {'engine':'Playwright Canvas frames + FFmpeg; not HyperFrames', 'fps':timeline['fps'], 'duration':timeline['duration'], 'cue_times':[c['time'] for c in cues], 'audio_correlations':correlations, 'seek_frame_hashes':seek, 'seek_order':'direct / reverse / cold reload match', 'full_decode':'passed', 'output_sha256':digest(output.read_bytes()), 'source_sha256':{f:digest((ROOT/f).read_bytes()) for f in ('index.html','timeline.json','ripple.js','kit-lp.js','assets/click.wav','assets.lock.json')}, 'listening_status':'pending', 'visual_review':'pending'}
        report.write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
