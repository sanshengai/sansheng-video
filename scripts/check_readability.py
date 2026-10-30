#!/usr/bin/env python3
"""可读性提示检查：字幕读速／时长／行数、屏幕文字停留、字号、术语出现。

全部是提示级，不拦截：正常运行退出码为 0；输入读不了或不是 JSON 时退出码为 2。
用法：python3 check_readability.py timeline.json [--brief brief.md]
      [--audience adult|learners] [--profile-dir 目录] [--film N] [--json]
读速上限可由 profile 的 delivery.caption_cps（default／learners）覆盖。
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# ---- 阈值：与 references/craft-defaults.md 「默认值」表保持一致 ----
READ_SPEED_MAX = {'adult': 9.0, 'learners': 7.0}   # 字幕读速上限（字/秒）
CAPTION_MIN_SECONDS = 1.8                           # 字幕单条时长下限
CAPTION_CHARS_PER_LINE = 16                         # 每行字数
CAPTION_MAX_LINES = 2                               # 最多行数
HOLD_MIN_SECONDS = 1.5                              # 停留公式：max(1.5, 字数/4.5 + 1.5)
HOLD_CHARS_PER_SECOND = 4.5  # 屏幕文字的阅读速度（字/秒），比字幕读速慢：观众同时要看画面
HOLD_PAD_SECONDS = 1.5       # 文字出现后找到它、开始读的反应时间
FONT_BASE_SHORT_SIDE = 1080                         # 字号按短边 1080 换算
FONT_MIN_PX = {'hook': 84, 'term': 48, 'cta': 48, None: 32}
FONT_TEXTURE_PX = 24                                # <24 只算纹理
LEARNER_WORDS = ('学生', '少儿', '儿童', '小学', '初中', 'learners')
EPS = 1e-9

_CJK = re.compile(
    r'[⺀-⿟぀-ヿ㄀-ㄯㆠ-ㇿ㐀-䶿'
    r'一-鿿가-힯豈-﫿\U00020000-\U0003134f]')
_WORD = re.compile(r'[A-Za-z0-9]+')


def count_chars(text):
    """中日韩字符每个 1；连续拉丁字母或数字串算 1；标点空白不计。"""
    text = text or ''
    return len(_CJK.findall(text)) + len(_WORD.findall(text))


def _num(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _notice(at, target, kind, message):
    return {'at': round(at, 3) if at is not None else None,
            'target': target, 'kind': kind, 'message': message}


def read_speed_limits(configuration):
    """profile 的 delivery.caption_cps 覆盖默认读速上限；缺项或非法值沿用默认。"""
    limits = dict(READ_SPEED_MAX)
    cps = ((configuration or {}).get('delivery') or {}).get('caption_cps')
    if isinstance(cps, dict):
        for key, aud in (('default', 'adult'), ('learners', 'learners')):
            v = cps.get(key)
            if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0:
                limits[aud] = float(v)
    return limits


def check_captions(events, audience, limits=None):
    out = []
    limit = (limits or READ_SPEED_MAX)[audience]
    for ev in events or []:
        if not isinstance(ev, dict):
            continue
        text = ev.get('caption')
        if not isinstance(text, str) or not text.strip():
            continue
        s, e = _num(ev.get('start')), _num(ev.get('end'))
        if s is None or e is None:
            continue
        n, dur = count_chars(text), e - s
        tid = str(ev.get('id', '?'))
        if n == 0:
            continue
        if dur <= 0:
            continue
        if n / dur > limit + EPS:
            need = n / limit
            out.append(_notice(s, tid, '读速',
                f'字幕 {n} 字 / {dur:.2f} 秒 = {n / dur:.1f} 字/秒，超过 {audience} 上限 {limit:g}。'
                f'建议拆成两条或延长到 {need:.1f} 秒。'))
        if dur < CAPTION_MIN_SECONDS - EPS:
            out.append(_notice(s, tid, '时长',
                f'字幕仅停留 {dur:.2f} 秒，短于 {CAPTION_MIN_SECONDS:g} 秒。建议延长到 {CAPTION_MIN_SECONDS:g} 秒以上或与相邻条合并。'))
        cap = CAPTION_CHARS_PER_LINE * CAPTION_MAX_LINES
        if n > cap:
            lines = -(-n // CAPTION_CHARS_PER_LINE)
            out.append(_notice(s, tid, '行数',
                f'字幕 {n} 字，按每行 {CAPTION_CHARS_PER_LINE} 字约 {lines} 行，超过 {CAPTION_MAX_LINES} 行。需要拆条。'))
    return out


def required_hold(n):
    return max(HOLD_MIN_SECONDS, n / HOLD_CHARS_PER_SECOND + HOLD_PAD_SECONDS)


def check_reads(shots, canvas):
    out = []
    short = None
    if (isinstance(canvas, (list, tuple)) and len(canvas) == 2
            and all(_num(x) and x > 0 for x in canvas)):
        short = min(canvas)
    for shot in shots or []:
        if not isinstance(shot, dict):
            continue
        sid = str(shot.get('id', '?'))
        for i, r in enumerate(shot.get('reads') or []):
            if not isinstance(r, dict):
                continue
            target = f'{sid}.read{i + 1}'
            s, e = _num(r.get('start')), _num(r.get('end'))
            reveal = _num(r.get('revealCompleteAt'))
            if reveal is None:
                reveal = s
            text = r.get('text')
            if isinstance(text, str) and text.strip() and e is not None and reveal is not None:
                n = count_chars(text)
                need, have = required_hold(n), e - reveal
                if have < need - EPS:
                    out.append(_notice(reveal, target, '停留',
                        f'屏幕文字 {n} 字，完全显示后只停留 {have:.2f} 秒，按公式应有 {need:.1f} 秒。'
                        f'建议延长到 {need:.1f} 秒或精简文字。'))
            px = _num(r.get('text_px'))
            if px is not None and short:
                norm = px * FONT_BASE_SHORT_SIDE / short
                role = r.get('role') if r.get('role') in ('hook', 'term', 'cta') else None
                at = s if s is not None else reveal
                if norm < FONT_TEXTURE_PX - EPS:
                    out.append(_notice(at, target, '字号',
                        f'字号换算到 1080 基准为 {norm:.0f} px，低于 {FONT_TEXTURE_PX}，只算纹理，不能当作要读的字。'))
                elif norm < FONT_MIN_PX[role] - EPS:
                    out.append(_notice(at, target, '字号',
                        f'字号换算到 1080 基准为 {norm:.0f} px，{role or "正文"}建议至少 {FONT_MIN_PX[role]} px。'))
    return out


def section(md, title):
    m = re.search(r'^##[ \t]+' + re.escape(title) + r'[ \t]*$', md, re.M)
    if not m:
        return ''
    rest = md[m.end():]
    n = re.search(r'^##[ \t]+', rest, re.M)
    return rest[:n.start()] if n else rest


FILM_LINE = re.compile(r'^\s*(?:[-*+]\s*)?第\s*(\d+)\s*条\s*[:：]\s*(.*)$')


def parse_terms(body, film=None):
    """拆出术语。系列制作单按「第 N 条：术语」逐条写，给 film 时只取那一条。"""
    body = body.strip()
    if not body or re.sub(r'[\s。.\-*「」]', '', body) == '无':
        return []
    lines = body.splitlines()
    if any(FILM_LINE.match(line) for line in lines):
        picked = [m.group(2) for m in map(FILM_LINE.match, lines)
                  if m and (film is None or int(m.group(1)) == film)]
        body = '\n'.join(picked)
    terms = []
    for part in re.split(r'[,，、;；\n]+', body):
        part = re.sub(r'^\s*(?:[-*+]|\d+[.、)])\s*', '', part).strip()
        part = part.strip('「」“”"\'`*。. ')
        if part and part != '无':
            terms.append(part)
    return terms


def check_terms(terms, events, shots):
    texts = []
    for ev in events or []:
        if isinstance(ev, dict) and isinstance(ev.get('caption'), str):
            texts.append(ev['caption'])
    for shot in shots or []:
        if isinstance(shot, dict):
            for r in shot.get('reads') or []:
                if isinstance(r, dict) and isinstance(r.get('text'), str):
                    texts.append(r['text'])
    blob = '\n'.join(texts).lower()
    return [_notice(None, f'术语「{t}」', '术语',
                    f'术语「{t}」未在字幕或画面文字中出现。建议在字幕或 reads 的 text 中显示它。')
            for t in terms if t.lower() not in blob]


NEGATION = re.compile(r'(非|不是|不含|无|不面向)$')


def _learner_word(text):
    """返回文中第一个未被否定的学生少儿词；「非学生」「不面向少儿」不算。"""
    for w in LEARNER_WORDS:
        for m in re.finditer(re.escape(w), text):
            if not NEGATION.search(text[max(0, m.start() - 4):m.start()]):
                return w
    return None


def pick_audience(arg, brief_text):
    if arg:
        return arg, '命令行 --audience'
    if brief_text is not None:
        ctx = section(brief_text, '观看情境')
        line = re.search(r'受众\s*[:：]\s*([^\n]+)', ctx)
        if line:
            w = _learner_word(line.group(1))
            return ('learners', f'制作单「受众：」含「{w}」') if w else ('adult', '制作单「受众：」未写学生少儿')
        w = _learner_word(ctx)
        if w:
            return 'learners', f'制作单「观看情境」含「{w}」'
        return 'adult', '制作单「观看情境」未提学生少儿，默认成人'
    return 'adult', '未给 --audience 与 --brief，默认成人'


def run(timeline, brief_text=None, audience=None, limits=None, film=None):
    aud, src = pick_audience(audience, brief_text)
    events = timeline.get('events') if isinstance(timeline, dict) else None
    shots = timeline.get('shots') if isinstance(timeline, dict) else None
    canvas = timeline.get('canvas') if isinstance(timeline, dict) else None
    notices = check_captions(events, aud, limits) + check_reads(shots, canvas)
    if brief_text is not None:
        notices += check_terms(parse_terms(section(brief_text, '术语'), film), events, shots)
    notices.sort(key=lambda n: (n['at'] is None, n['at'] or 0))
    return {'audience': aud, 'audience_source': src, 'notices': notices, 'count': len(notices)}


def main(argv=None):
    ap = argparse.ArgumentParser(description='可读性提示检查（提示级，不拦截）')
    ap.add_argument('timeline')
    ap.add_argument('--brief')
    ap.add_argument('--audience', choices=('adult', 'learners'))
    ap.add_argument('--profile-dir')
    ap.add_argument('--film', type=int, help='系列制作单里只核对第 N 条的术语')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args(argv)
    try:
        timeline = json.loads(Path(a.timeline).read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        print(f'无法读取时间线 {a.timeline}：{exc}', file=sys.stderr)
        return 2
    brief_text = None
    if a.brief:
        try:
            brief_text = Path(a.brief).read_text(encoding='utf-8')
        except OSError as exc:
            print(f'无法读取制作单 {a.brief}：{exc}', file=sys.stderr)
            return 2
    try:
        sys.path.insert(0, str(ROOT))
        from setup import profile  # setup.py 的 main 受 __name__ 保护
        prof = profile(a.profile_dir)
    except (OSError, ValueError) as exc:
        print(f'profile 读取失败：{exc}', file=sys.stderr)
        return 2
    res = run(timeline, brief_text, a.audience, read_speed_limits(prof['configuration'] if prof else None), a.film)
    if a.json:
        print(json.dumps({'audience': res['audience'], 'notices': res['notices'],
                          'count': res['count']}, ensure_ascii=False, indent=2))
    else:
        print(f"受众：{res['audience']}（{res['audience_source']}）")
        for n in res['notices']:
            at = '--' if n['at'] is None else f"{n['at']:.2f}s"
            print(f"[{at}] {n['target']} {n['kind']}：{n['message']}")
        print(f"共 {res['count']} 条提示（提示级，不拦截）。")
    return 0


if __name__ == '__main__':
    sys.exit(main())
