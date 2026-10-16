#!/usr/bin/env python3
"""Local, optional TTS adapters. One model load; real chunk boundaries, no approval."""
import argparse
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import time
import wave

MODELS = {
    'voxcpm2': ('openbmb/VoxCPM2', '32279effe8c19989596f05d353d1447f51d9e915'),
    'kokoro': ('hexgrad/Kokoro-82M', 'f3ff3571791e39611d31c381e3a41a3af07b4987'),
}


def validate(data):
    if data.get('engine') not in MODELS:
        raise ValueError('engine must be voxcpm2 or kokoro')
    blocks = data.get('blocks')
    if not isinstance(blocks, list) or not blocks or len(blocks) > 100:
        raise ValueError('provide 1..100 explicit narration blocks')
    if any(not isinstance(s, str) or not s.strip() or len(s) > 400 for s in blocks):
        raise ValueError('blocks must be nonempty strings, at most 400 characters each')
    if not isinstance(data.get('seed', 42), int) or isinstance(data.get('seed'), bool):
        raise ValueError('seed must be an integer')
    if data.get('reference') and (data['engine'] != 'voxcpm2' or not data.get('reference_rights')):
        raise ValueError('reference requires voxcpm2 and an explicit reference_rights statement')
    if data['engine'] == 'kokoro':
        voice, lang = data.get('voice', 'af_heart'), data.get('language', 'a')
        if lang not in ('a', 'b', 'z') or not isinstance(voice, str) or not voice.startswith(lang) or not voice.replace('_', '').isalnum():
            raise ValueError('Kokoro voice must match language a/b/z; no paths or blends')
    return blocks


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def backend(data, allow_download, base):
    import numpy as np
    import torch
    from huggingface_hub import hf_hub_download, snapshot_download
    engine = data['engine']; repo, revision = MODELS[engine]
    device = data.get('device', 'mps' if torch.backends.mps.is_available() else 'cpu')
    seed = data.get('seed', 42)
    reference = (base / data['reference']).resolve() if data.get('reference') else None
    metadata = {'engine': engine, 'model': repo, 'revision': revision, 'device': device,
                'seed': seed, 'torch': version('torch')}
    if engine == 'voxcpm2':
        from voxcpm import VoxCPM
        metadata['package'] = version('voxcpm')
        if metadata['package'] != '2.0.3':
            raise ValueError('validated adapter requires voxcpm==2.0.3; validate upgrades separately')
        model_path = snapshot_download(repo, revision=revision, ignore_patterns=['*.md', '.gitattributes'],
                                       local_files_only=not allow_download, max_workers=3)
        model = VoxCPM.from_pretrained(model_path, load_denoiser=False, device=device,
                                      optimize=False, local_files_only=True)
        if reference:
            metadata['reference_sha256'] = digest(reference)
        control = data.get('control', 'Warm, clear adult voice, natural explanatory delivery')
        anchor = [str(reference) if reference else None]
        def generate(text, previous_path):
            torch.manual_seed(seed)
            if anchor[0] is None and previous_path:
                anchor[0] = str(previous_path)
            # PyPI 2.0.3 has no seed kwarg; set torch RNG explicitly.
            wav = model.generate(text=f'({control}){text}', reference_wav_path=anchor[0],
                                 inference_timesteps=10, max_len=2048, retry_badcase=False)
            return np.asarray(wav), model.tts_model.sample_rate
    else:
        from kokoro import KModel, KPipeline
        metadata['package'] = version('kokoro')
        if metadata['package'] != '0.9.4':
            raise ValueError('validated adapter requires kokoro==0.9.4')
        voice = data.get('voice', 'af_heart'); lang = data.get('language', 'a')
        def download(name):
            return hf_hub_download(repo, name, revision=revision, local_files_only=not allow_download)
        if lang in ('a', 'b'):
            import spacy
            if not spacy.util.is_package('en_core_web_sm'):
                raise ValueError('Install spaCy en_core_web_sm in the TTS venv first; implicit installation is disabled')
        model = KModel(repo_id=repo, config=download('config.json'), model=download('kokoro-v1_0.pth')).to(device)
        voice_path = download('voices/' + voice + '.pt')
        pipeline = KPipeline(lang_code=lang, model=model, device=device, repo_id=repo)
        metadata.update(voice=voice, language=lang)
        def generate(text, previous_path):
            torch.manual_seed(seed)
            parts = [a.detach().cpu().numpy() for _, _, a in pipeline(text, voice=voice_path, speed=1)]
            if not parts:
                raise ValueError('Kokoro returned no speech')
            return np.concatenate(parts), 24000
    return generate, metadata


def run(manifest, output, allow_download=False):
    manifest = Path(manifest).resolve(); raw = manifest.read_bytes(); data = json.loads(raw)
    blocks = validate(data)
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    import numpy as np
    import soundfile as sf
    generate, metadata = backend(data, allow_download, manifest.parent)
    chunks = []; frames = []; previous = None; at = 0; sample_rate = None
    for i, text in enumerate(blocks):
        started = time.monotonic()
        audio, sr = generate(text, previous)
        if audio.ndim != 1 or not np.isfinite(audio).all() or len(audio) == 0 or not np.any(audio):
            raise ValueError('invalid, empty or silent speech')
        if sample_rate is not None and sr != sample_rate:
            raise ValueError('sample rate changed between blocks')
        sample_rate = sr
        path = output / f'block-{i:03d}.wav'
        sf.write(path, audio, sr, subtype='PCM_16')
        # Use written PCM samples, also for the final assembly.
        pcm, _ = sf.read(path, dtype='int16'); frames.append(pcm.tobytes())
        length = len(pcm) / sr
        chunks.append({'text': text, 'at': at, 'duration': length, 'path': path.name,
                       'sha256': digest(path), 'generation_seconds': time.monotonic() - started})
        at += length
        if previous is None:
            previous = path
    final = output / 'narration.wav'
    with wave.open(str(final), 'wb') as stream:
        stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(sample_rate)
        stream.writeframes(b''.join(frames))
    record = {'kind': 'tts-production/1', 'created_at': datetime.now(timezone.utc).isoformat(),
              'manifest_sha256': hashlib.sha256(raw).hexdigest(), 'settings': data,
              'backend': metadata, 'path': final.name, 'sha256': digest(final), 'duration': at,
              'text': ''.join(blocks), 'chunks': chunks, 'listening_status': 'pending',
              'word_alignment': 'none; chunk boundaries only'}
    record_path = output / 'production.json'
    record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
    from production_narration import import_evidence
    evidence = import_evidence(record_path, final)
    (output / 'narration-evidence.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n')
    return {'audio': str(final), 'record': str(record_path), 'duration': at, 'blocks': len(chunks)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest'); parser.add_argument('--out', required=True)
    parser.add_argument('--allow-download', action='store_true', help='Permit pinned model downloads')
    args = parser.parse_args()
    print(json.dumps(run(args.manifest, args.out, args.allow_download), ensure_ascii=False, indent=2))
