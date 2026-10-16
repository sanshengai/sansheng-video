#!/usr/bin/env python3
"""Explicit local narration/music mix; interval ducking, never human approval.

Uses FFmpeg and the existing normalize_loudness optional consumer. Speech
intervals are caller-supplied block anchors, not detected/word-aligned speech.
A production parent can produce a compatible *derived* render receipt without
modifying its original receipt or claiming that another visual render occurred.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(command):
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        raise ValueError('media command failed: ' + result.stderr[-1800:])
    return result.stdout


def probe(path):
    return json.loads(run(['ffprobe', '-v', 'error', '-show_format', '-show_streams',
                           '-of', 'json', str(path)]))


def video_hash(path):
    """Hash copied compressed video packets, excluding container metadata."""
    return run(['ffmpeg', '-v', 'error', '-i', str(path), '-map', '0:v:0',
                '-c:v', 'copy', '-f', 'hash', '-hash', 'sha256', '-']).strip()


def finite(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(label + ' must be finite')
    return float(value)


def mix(video, narration, music, output, speech_intervals, *, source_audio='reject',
        music_gain=.15, duck_gain=.03, narration_gain=1., normalize_lufs=None,
        parent_receipt=None, attack=.1, release=.25, narration_offset=0.):
    """Mix music at t=0, narration at its explicit offset; never truncate.

    source_audio: reject (default), preserve (add original lane), or replace
    (explicit discard). Intervals are [start,end] seconds in the video timeline.
    No looping, inferred alignment, automatic approval or source overwrites.
    """
    video, narration, music, output = (Path(p).resolve() for p in (video, narration, music, output))
    if source_audio not in {'reject', 'preserve', 'replace'}:
        raise ValueError('unknown source_audio policy')
    for label, value in [('music_gain', music_gain), ('duck_gain', duck_gain), ('narration_gain', narration_gain)]:
        if not 0 <= finite(value, label) <= 2:
            raise ValueError(label + ' outside 0..2')
    if duck_gain >= music_gain:
        raise ValueError('duck gain must be lower than music gain')
    attack, release = finite(attack, 'attack'), finite(release, 'release')
    if attack <= 0 or release <= 0:
        raise ValueError('attack and release must be positive seconds')
    narration_offset = finite(narration_offset, 'narration_offset')
    if narration_offset < 0:
        raise ValueError('narration_offset must be nonnegative seconds')
    receipt_path = output.with_suffix('.mix.json')
    render_path = output.with_suffix('.render.json')
    inputs = {str(p): digest(p) for p in (video, narration, music, Path(__file__).resolve())}
    if output in (video, narration, music) or output.exists() or receipt_path.exists() or render_path.exists():
        raise ValueError('use a new output; never overwrite sources or receipts')
    if output.suffix != '.mp4':
        raise ValueError('output must be MP4')
    infos = [probe(p) for p in (video, narration, music)]
    videos = [s for s in infos[0]['streams'] if s['codec_type'] == 'video']
    if len(videos) != 1:
        raise ValueError('exactly one video stream required')
    duration = finite(float(videos[0].get('duration', infos[0]['format']['duration'])), 'video duration')
    if duration <= 0:
        raise ValueError('empty video')
    source_tracks = [s for s in infos[0]['streams'] if s['codec_type'] == 'audio']
    if len(source_tracks) > 1:
        raise ValueError('multiple original audio streams require explicit prior selection')
    if source_tracks and source_audio == 'reject':
        raise ValueError('source has audio: explicitly preserve or replace it')
    for label, info in zip(('narration', 'music'), infos[1:]):
        tracks = [s for s in info['streams'] if s['codec_type'] == 'audio']
        if len(tracks) != 1:
            raise ValueError(label + ' requires exactly one audio stream')
        if abs(float(tracks[0].get('start_time', 0))) > .001:
            raise ValueError(label + ' must start at zero')
    voice_duration = float(infos[1]['format']['duration'])
    if narration_offset + voice_duration > duration + .05 or float(infos[2]['format']['duration']) < duration - .001:
        raise ValueError('narration exceeds video or music does not cover video; no implicit truncation/loop')
    intervals, previous = [], 0.
    if not isinstance(speech_intervals, list) or not speech_intervals:
        raise ValueError('nonempty explicit speech intervals required')
    for pair in speech_intervals:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise ValueError('speech interval must be [start,end]')
        start, end = (finite(v, 'speech interval') for v in pair)
        if start < max(previous, narration_offset) or end <= start or end > min(duration, narration_offset + voice_duration) + .001:
            raise ValueError('speech intervals overlap or exceed narration/video')
        intervals.append([start, end]); previous = end
    parent = None
    if parent_receipt:
        from render_production import verify
        parent_receipt = Path(parent_receipt).resolve()
        verify(parent_receipt)
        parent = json.loads(parent_receipt.read_text())
        if Path(parent['output']).resolve() != video:
            raise ValueError('parent render must bind the input video')
        inputs[str(parent_receipt)] = digest(parent_receipt)
    if normalize_lufs is not None:
        from normalize_loudness import _validate_target_lufs
        _validate_target_lufs(normalize_lufs)
        inputs[str(Path(__file__).with_name('normalize_loudness.py').resolve())] = digest(Path(__file__).with_name('normalize_loudness.py'))
    # Sample-wise linear envelopes: pre-duck before each known start, then
    # release after its end. The lowest envelope wins when ramps overlap.
    # Anchors remain caller-supplied blocks, never inferred word timings.
    gain = str(music_gain)
    delta = music_gain - duck_gain
    for start, end in intervals:
        envelope = (f'if(lt(t,{start}),{music_gain}-{delta}*'
                    f'clip((t-({start}-{attack}))/{attack},0,1),'
                    f'{duck_gain}+{delta}*clip((t-{end})/{release},0,1))')
        gain = f'min({gain},{envelope})'
    channels = next(s['channels'] for s in infos[2]['streams'] if s['codec_type'] == 'audio')
    expressions = '|'.join(f'val({channel})*({gain})' for channel in range(channels))
    filters = [f"[1:a:0]adelay={narration_offset*1000}:all=1,volume={narration_gain},apad=whole_dur={duration},atrim=duration={duration}[voice]",
               f"[2:a:0]aeval='{expressions}',atrim=duration={duration}[bed]"]
    lanes = '[voice][bed]'
    if source_tracks and source_audio == 'preserve':
        filters.append(f'[0:a:0]apad=whole_dur={duration},atrim=duration={duration}[original]')
        lanes += '[original]'
    count = 3 if source_tracks and source_audio == 'preserve' else 2
    filters.append(f'{lanes}amix=inputs={count}:duration=longest:normalize=0[mix]')
    commands = []
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='audio-mix-', dir=output.parent) as temp:
        candidate = Path(temp) / 'mixed.mp4'
        command = ['ffmpeg', '-v', 'error', '-nostdin', '-i', str(video), '-i', str(narration), '-i', str(music),
                   '-filter_complex', ';'.join(filters), '-map', '0:v:0', '-map', '[mix]', '-c:v', 'copy',
                   '-c:a', 'aac', '-b:a', '192k', '-t', str(duration), '-movflags', '+faststart', str(candidate)]
        run(command); commands.append(command)
        if normalize_lufs is not None:
            from normalize_loudness import normalize_loudness
            normalized = Path(temp) / 'normalized.mp4'
            normalize_loudness(str(candidate), normalize_lufs, output_path=str(normalized))
            commands.append(['ffmpeg', '-hide_banner', '-y', '-i', str(candidate), '-c:v', 'copy',
                             '-af', f'loudnorm=I={normalize_lufs}:TP=-1.5:LRA=11.0', '-c:a', 'aac', '-b:a', '192k', str(normalized)])
            candidate = normalized
        result = probe(candidate)
        if abs(float(result['format']['duration']) - duration) > .06:
            raise ValueError('mixed output duration changed')
        run(['ffmpeg', '-v', 'error', '-xerror', '-i', str(candidate), '-f', 'null', '-'])
        before_video, after_video = video_hash(video), video_hash(candidate)
        if before_video != after_video:
            raise ValueError('video packets changed')
        if any(digest(p) != sha for p, sha in inputs.items()):
            raise ValueError('mix input changed')
        if parent_receipt:
            verify(parent_receipt)
        shutil.move(candidate, output)
    receipt = {'kind': 'production-audio-mix/1', 'status': 'mixed_not_reviewed',
               'inputs': inputs, 'output': str(output), 'output_sha256': digest(output),
               'commands': commands, 'source_audio': source_audio, 'speech_intervals': intervals,
               'music_gain': music_gain, 'duck_gain': duck_gain, 'narration_gain': narration_gain,
               'attack': attack, 'release': release, 'duck_envelope': 'sample_linear_minimum',
               'narration_offset': narration_offset,
               'normalize_lufs': normalize_lufs, 'video_packets_sha256': after_video,
               'duration': duration, 'anchor_basis': 'caller_supplied_block_intervals_not_word_alignment'}
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    if parent:
        # The existing verifier accepts postproduction-derived output when the
        # actual parent build/runtime and all new inputs remain bound.
        parent_command = parent.get('command')
        parent.update(operation='audio-mix', status='mixed_not_reviewed', output=str(output),
                      output_sha256=digest(output), command=commands,
                      parent_receipt=str(parent_receipt), parent_receipt_sha256=inputs[str(parent_receipt)],
                      parent_command=parent_command, mix_receipt=str(receipt_path))
        parent['runtime_files'].update(inputs)
        parent['runtime_files'][str(receipt_path)] = digest(receipt_path)
        parent['verification'] = {'duration': float(result['format']['duration']), 'full_decode': True,
                                  'has_audio': True, 'width': videos[0]['width'], 'height': videos[0]['height'],
                                  'video_packets_unchanged': True}
        render_path.write_text(json.dumps(parent, ensure_ascii=False, indent=2) + '\n')
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('video', 'narration', 'music', 'output', 'intervals'):
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--source-audio', choices=('reject', 'preserve', 'replace'), default='reject')
    parser.add_argument('--music-gain', type=float, default=.15)
    parser.add_argument('--duck-gain', type=float, default=.03)
    parser.add_argument('--narration-gain', type=float, default=1.)
    parser.add_argument('--attack', type=float, default=.1)
    parser.add_argument('--release', type=float, default=.25)
    parser.add_argument('--narration-offset', type=float, default=0.)
    parser.add_argument('--normalize-lufs', type=float)
    parser.add_argument('--parent-receipt', type=Path)
    parser.add_argument('--_worker', action='store_true', help=argparse.SUPPRESS)
    args = vars(parser.parse_args())
    if not args.pop('_worker'):
        from runtime_support import managed_command
        # Only the outer CLI acquires the managed slot. API callers own theirs.
        command = [sys.executable, '-B', str(Path(__file__).resolve()), *sys.argv[1:], '--_worker']
        return subprocess.run(managed_command(command)).returncode
    args['speech_intervals'] = json.loads(args.pop('intervals').read_text())
    print(json.dumps(mix(**args), ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
