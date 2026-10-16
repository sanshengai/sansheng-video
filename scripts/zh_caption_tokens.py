#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""zh_caption_tokens.py -- 中文卡拉OK字幕 token 整形器

把 whisper / OpenAI verbose JSON（段级或词级）整形成卡拉OK字幕组件
(caption-pill-karaoke-zh.html) 消费的扁平词数组::

    [{"text": "这个", "start": 0.30, "end": 0.62}, ...]

核心逻辑
  a) 已有词级且词长合理（CJK ≤4 字）的 token 直接通过；
  b) 中文整段坍缩成长 token（whisper.cpp normalize 空格断词 bug）时，
     用 jieba 分词切开（import 失败退化为逐字），时间按字符数线性插值；
  c) 半角/全角标点（，。！？：；、 等）并入前一个词，不单独成 token。

支持的输入形状（自动识别）
  - OpenAI verbose_json 顶层 "words": [{word,start,end}]
  - OpenAI/whisper "segments": [...]，段内有 "words" 用词级，没有用段级切分
  - whisper.cpp "transcription": [{offsets:{from,to}(ms), text}]
  - 已是扁平数组 [{text|word, start, end}]（幂等，只做长词切分+标点归并）

用法（Windows 必须 PYTHONUTF8=1）::

    pip install jieba                                # 一次性依赖
    set PYTHONUTF8=1
    python zh_caption_tokens.py transcript.json -o tokens.json
    python zh_caption_tokens.py transcript.json      # 不给 -o 则打印到 stdout
    type transcript.json | python zh_caption_tokens.py -

依赖: jieba（可选，缺失时退化为逐字切分并打 warning）
"""

import argparse
import json
import sys

try:
    import jieba

    _HAS_JIEBA = True
except ImportError:  # 退化路径：逐字切分
    jieba = None
    _HAS_JIEBA = False

# 并入前词的标点（半角 + 全角）；不含空格
PUNCT = set("，。！？：；、…—·“”‘’（）《》【】,.!?:;\"'()[]")


def is_cjk(ch):
    code = ord(ch)
    return (
        0x4E00 <= code <= 0x9FFF
        or 0x3400 <= code <= 0x4DBF
        or 0xF900 <= code <= 0xFAFF
    )


def cjk_len(text):
    return sum(1 for ch in text if is_cjk(ch))


def _f(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def extract_raw_tokens(data):
    """把各种 whisper/OpenAI JSON 形状统一成 [{text,start,end}]（未切分）。"""
    # 已是扁平数组
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        if isinstance(data.get("words"), list) and data["words"]:
            items = data["words"]
        elif isinstance(data.get("segments"), list):
            items = []
            for seg in data["segments"]:
                words = seg.get("words")
                if isinstance(words, list) and words:
                    items.extend(words)
                else:
                    items.append(seg)
        elif isinstance(data.get("transcription"), list):  # whisper.cpp
            items = []
            for seg in data["transcription"]:
                offs = seg.get("offsets") or {}
                items.append(
                    {
                        "text": seg.get("text", ""),
                        "start": _f(offs.get("from")) / 1000.0,
                        "end": _f(offs.get("to")) / 1000.0,
                    }
                )
        else:
            raise ValueError("无法识别的 JSON 形状：缺 words/segments/transcription")
    else:
        raise ValueError("输入必须是 JSON 数组或对象")

    tokens = []
    for item in items:
        text = str(item.get("word") or item.get("text") or "").strip()
        if not text:
            continue
        start = _f(item.get("start"))
        end = max(start, _f(item.get("end"), start))
        tokens.append({"text": text, "start": start, "end": end})
    return tokens


def split_long_token(token, max_len):
    """长中文 token 按 jieba（或逐字）切开，时间按字符数线性插值。"""
    text = token["text"]
    start, end = token["start"], token["end"]
    total = len(text)
    dur = max(end - start, 0.0)

    if _HAS_JIEBA:
        pieces = list(jieba.cut(text))  # 保序、覆盖全部字符（含空格/标点）
    else:
        pieces = list(text)

    out = []
    pos = 0
    for piece in pieces:
        ln = len(piece)
        p_start = start + dur * pos / total
        p_end = start + dur * (pos + ln) / total
        pos += ln
        if not piece.strip():
            continue  # 空白片段只占时间，不出 token
        # jieba 偶尔吐 >max_len 的词（成语/专名），再按 max_len 直切
        if cjk_len(piece) > max_len and ln > max_len:
            p_dur = p_end - p_start
            for i in range(0, ln, max_len):
                chunk = piece[i : i + max_len]
                out.append(
                    {
                        "text": chunk,
                        "start": p_start + p_dur * i / ln,
                        "end": p_start + p_dur * min(i + max_len, ln) / ln,
                    }
                )
        else:
            out.append({"text": piece, "start": p_start, "end": p_end})
    return out


def merge_punctuation(tokens):
    """纯标点 token / token 开头的标点 → 并入前一个词。"""
    out = []
    for tok in tokens:
        text = tok["text"]
        # 开头连续标点先并给前词
        while text and text[0] in PUNCT and out:
            out[-1]["text"] += text[0]
            text = text[1:]
        if not text:  # 整个 token 都是标点：吃掉，时间并给前词
            if out:
                out[-1]["end"] = max(out[-1]["end"], tok["end"])
            continue
        out.append({"text": text, "start": tok["start"], "end": tok["end"]})
    return out


def process(data, max_len=4):
    raw = extract_raw_tokens(data)
    flat = []
    for tok in raw:
        if cjk_len(tok["text"]) > max_len:  # 坍缩长段（或超长词）→ 切
            flat.extend(split_long_token(tok, max_len))
        else:  # 词级且词长合理 → 直接通过
            flat.append(tok)
    flat = merge_punctuation(flat)
    for tok in flat:  # 收尾：时间取整到毫秒、保证 end>=start
        tok["start"] = round(tok["start"], 3)
        tok["end"] = round(max(tok["end"], tok["start"]), 3)
    return flat


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="whisper/OpenAI verbose JSON → 中文卡拉OK扁平词数组 [{text,start,end}]",
        epilog=(
            "示例:\n"
            "  set PYTHONUTF8=1\n"
            "  python zh_caption_tokens.py transcript.json -o tokens.json\n"
            "  type transcript.json | python zh_caption_tokens.py -\n"
            "产物直接粘贴进 caption-pill-karaoke-zh.html 的 TRANSCRIPT 数组。"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("input", help="输入 JSON 文件路径，- 表示读 stdin")
    parser.add_argument("-o", "--output", help="输出文件路径（默认打印到 stdout）")
    parser.add_argument(
        "--max-len",
        type=int,
        default=4,
        help="词级 token 允许的最大 CJK 字数，超过即触发切分（默认 4）",
    )
    args = parser.parse_args(argv)

    if not _HAS_JIEBA:
        print("[warn] jieba 不可用（pip install jieba），退化为逐字切分", file=sys.stderr)

    if args.input == "-":
        data = json.load(sys.stdin)
    else:
        with open(args.input, "r", encoding="utf-8-sig") as fh:
            data = json.load(fh)

    tokens = process(data, max_len=args.max_len)
    rendered = json.dumps(tokens, ensure_ascii=False, indent=2)

    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(rendered + "\n")
        print("[ok] %d tokens -> %s" % (len(tokens), args.output), file=sys.stderr)
    else:
        print(rendered)


if __name__ == "__main__":
    main()
