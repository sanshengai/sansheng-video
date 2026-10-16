"""Portable runtime support; no implicit installation or global skill updates."""
from pathlib import Path
from datetime import datetime, timezone
import json, math, os, re, shutil, subprocess
RENDERER = {"version": "0.8.72", "fps": 30}
SKILL = Path(__file__).resolve().parents[1]
def utcnow():
    return datetime.now(timezone.utc).isoformat()

def locate_renderer(runtime=None):
    candidates = [Path(runtime)] if runtime else [SKILL / "node_modules/hyperframes"] + sorted(
        (Path.home() / ".npm/_npx").glob("*/node_modules/hyperframes"))
    for root in candidates:
        package = root / "package.json"
        if not package.is_file():
            continue
        spec = json.loads(package.read_text())
        cli = root / "bin/hyperframes.mjs"
        if spec.get("name") == "hyperframes" and spec.get("version") == RENDERER["version"] and cli.is_file():
            node = shutil.which("node")
            if not node:
                raise RuntimeError("固定渲染器需要 Node.js >=22")
            version = subprocess.run([node, "--version"], capture_output=True, text=True, check=True).stdout.strip()
            if not re.fullmatch(r"v\d+\.\d+\.\d+", version) or int(version[1:].split(".")[0]) < 22:
                raise RuntimeError("固定渲染器需要 Node.js >=22")
            return [node, str(cli.resolve())]
    raise RuntimeError("本机未找到 HyperFrames 0.8.72；不自动下载，安装后用 --runtime 指向包目录")

def managed_command(command):
    """Use an explicitly configured local scheduler, or execute directly.

    The wrapper is a JSON argv prefix, never evaluated as shell source.
    It must forward arguments, own its scheduling and propagate exit status.
    """
    raw = os.environ.get("SANSHENG_VIDEO_COMMAND_PREFIX")
    if not raw:
        return list(command)
    prefix = json.loads(raw)
    if not isinstance(prefix, list) or not prefix or any(not isinstance(x, str) or not x for x in prefix):
        raise ValueError("SANSHENG_VIDEO_COMMAND_PREFIX must be a nonempty JSON string array")
    return prefix + list(command)

def verify_clip(path, job):
    ffprobe, ffmpeg = shutil.which("ffprobe"), shutil.which("ffmpeg")
    if not ffprobe or not ffmpeg:
        raise RuntimeError("片段验收需要 ffprobe 与 ffmpeg")
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError("渲染没有产生有效片段")
    probe = subprocess.run([ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                           capture_output=True, text=True, timeout=60)
    if probe.returncode:
        raise ValueError("片段 ffprobe 失败：" + probe.stderr[-500:])
    info = json.loads(probe.stdout)
    streams = [s for s in info.get("streams", []) if s.get("codec_type") == "video"]
    duration = float(info.get("format", {}).get("duration", 0))
    if (len(streams) != 1 or streams[0].get("width") != job["width"] or
            streams[0].get("height") != job["height"] or not math.isfinite(duration) or
            abs(duration - job["duration"]) > max(.08, 2 / RENDERER["fps"])):
        raise ValueError("片段画幅/时长不符合实例计划")
    rate = streams[0].get("avg_frame_rate", "0/1").split("/")
    if len(rate) != 2 or float(rate[1]) == 0 or abs(float(rate[0]) / float(rate[1]) - RENDERER["fps"]) > .01:
        raise ValueError("片段帧率不符合固定渲染契约")
    decode = subprocess.run([ffmpeg, "-v", "error", "-xerror", "-i", str(path), "-map", "0:v:0", "-f", "null", "-"],
                            capture_output=True, text=True, timeout=max(60, job["duration"] * 10))
    if decode.returncode or decode.stderr.strip():
        raise ValueError("片段完整解码失败：" + decode.stderr[-500:])
    return {"width": job["width"], "height": job["height"], "duration": duration,
            "fps": RENDERER["fps"], "full_decode": True, "checked_at": utcnow()}
