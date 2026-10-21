#!/usr/bin/env python3
"""Render a bounded selected-artwork preview; not a finished promotional film."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import subprocess
import tempfile

import select_assets


def render(lock, output, seconds=1.5, fps=24):
    from PIL import Image, ImageOps, ImageDraw
    if type(seconds) not in (int, float) or not math.isfinite(seconds) or not .25 <= seconds <= 3:
        raise ValueError('per-image seconds must be .25..3')
    if type(fps) is not int or not 1 <= fps <= 30:
        raise ValueError('fps must be 1..30')
    data, inputs = select_assets.verified(lock)
    if len(data['items']) > 12 or len(data['items'])*seconds > 24:
        raise ValueError('bounded preview: at most 12 images / 24 seconds')
    width, height = data['canvas']
    if width % 2 or height % 2:
        raise ValueError('H264 preview requires even canvas dimensions')
    output = Path(output).resolve()
    if output.exists() or output.with_suffix('.preview.json').exists():
        raise ValueError('preview output exists; choose new version')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.selection-preview-', dir=output.parent) as temporary:
        movie = Path(temporary)/'preview.mp4'
        command = ['ffmpeg', '-v', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{width}x{height}',
                   '-r', str(fps), '-i', '-', '-an', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20',
                   '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(movie)]
        with tempfile.TemporaryFile() as errors:
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=errors)
            try:
                frames = max(1, round(seconds*fps))
                for index, item in enumerate(data['items']):
                    with Image.open(item['file']) as original:
                        image = ImageOps.exif_transpose(original).convert('RGB')
                        box = (round(width*.9), round(height*.86))
                        if item['fit'] == 'cover':
                            image = ImageOps.fit(image, box, centering=tuple(item['focal']))
                        else:
                            image = ImageOps.contain(image, box)
                    for frame in range(frames):
                        canvas = Image.new('RGB', (width, height), '#161819')
                        # Gentle entrance uses the whole artwork at its native ratio.
                        progress = min(1, frame / max(1, fps*.25))
                        offset = round(height*.025*(1-progress)**3)
                        canvas.paste(image, ((width-image.width)//2, (height-image.height)//2+offset))
                        ImageDraw.Draw(canvas).text((round(width*.05), round(height*.025)),
                                                    f'{index+1:02d} / {len(data["items"]):02d}', fill='white')
                        process.stdin.write(canvas.tobytes())
                process.stdin.close()
                code = process.wait(timeout=90)
                errors.seek(0); message = errors.read().decode(errors='replace')
                if code:
                    raise ValueError('preview encode failed: '+message[-2000:])
            except BaseException:
                process.kill(); process.wait(); raise
        # Do not publish an output if a source changed during the actual render.
        for path, expected in inputs.items():
            if not Path(path).is_file() or select_assets.digest(path) != expected:
                raise ValueError('preview input changed during render: '+path)
        subprocess.run(['ffmpeg', '-v', 'error', '-xerror', '-i', str(movie), '-f', 'null', '-'],
                       check=True, capture_output=True, timeout=60)
        report = {'kind': 'asset-selection-preview/1', 'status': 'technical_preview_not_aesthetic_approval',
                  'inputs': {**inputs, str(Path(__file__).resolve()): select_assets.digest(__file__)},
                  'video': str(output), 'sha256': select_assets.digest(movie), 'canvas': data['canvas'],
                  'fps': fps, 'frames_per_item': frames,
                  'shots': [{'index': i, 'asset_id': item['asset_id'], 'file': item['file'],
                             'sha256': item['sha256'], 'start_frame': i*frames, 'end_frame': (i+1)*frames-1}
                            for i, item in enumerate(data['items'])]}
        movie.rename(output)
        output.with_suffix('.preview.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('lock'); parser.add_argument('output'); parser.add_argument('--seconds', type=float, default=1.5)
    parser.add_argument('--fps', type=int, default=24)
    args = parser.parse_args()
    report = render(args.lock, args.output, args.seconds, args.fps)
    print(json.dumps({key: report[key] for key in ('video', 'sha256', 'canvas', 'status')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
