# sansheng-video EDL JSON Schema（scene 序列剪辑决策表）

> EDL（Edit Decision List）= sansheng-video 出片管线里**一条 scene 序列的剪辑决策表**：
> 每个 scene 决定「这段时间线上，放哪个 source 的哪一段，配哪句口播」。
> 它是 `scripts/validate_edl.py` 的机检输入；既有媒体编辑由
> `scripts/assemble_edl.py` 消费，结构检查后仍需审看实际成片。
>
> 概念溯源：转译自 guigulaoshi/music-video-director-skill 的 cuts/EDL（MIT，
> 锁定 commit `06abf674`，见 [UPSTREAM-REFERENCES.md](sources.md)）。
> 上游 beats 字段转译为可选 word_ts；只有实际验证的词级对齐来源才能填写。
>
> 🔴 **命名红线（2026-06-07）**：这里的「EDL」= sansheng-video 自创 JSON（秒 / `scenes` / `source` 的 ffmpeg concat 决策表），**≠ 业界 CMX3600 `.edl` 文本**。**严禁把本 JSON 直接喂 DaVinci MCP `timeline import_timeline_checked {format:edl}`（格式不兼容必失败）**——后者只吃标准 CMX3600/AAF/FCPXML/DRT/OTIO。两边同名「EDL」是完全不同的东西。要进达芬奇 timeline 需另写 JSON→CMX3600 桥（秒×fps 转源时码 + 事件号 + 源名），属低优先 backlog（详见 [media-editing.md](media-editing.md) §v2.36 增订 §3）。

---

## 顶层结构

```jsonc
{
  "metadata": {
    "total_duration": 62.5,   // 计划成片总时长（秒），校验④覆盖用
    "fps": 30.0,              // 实际装配帧率，校验⑦⑧的帧换算基准
    "word_ts": [ ... ]        // 可选：有已验证词级时间戳时才填写，无则省略；
                              //   scene 自带 word_ts 优先，不用块锚/估时冒充词级对齐
  },
  "audio_mode": "source",              // 保留各源片声音；此时不能提供 audio_file
  "output_file": "成片.mp4",
  "scenes": [ /* scene 对象数组，见下 */ ]
}
```

`metadata.total_duration` / `metadata.fps` / `metadata.word_ts` 也可在调用
`validate_edl()` 或 CLI `--total/--fps` 时显式覆盖；都不给则跳过依赖它们的校验项。

## scene 对象字段

| 字段 | 类型 | 必填 | 含义 |
|---|---|---|---|
| `n` | int | 建议 | scene 序号（报错信息引用；缺省用数组下标 +1）|
| `timeline_start` | float(秒) | 是 | 在成片时间线上的入场时刻 |
| `timeline_end` | float(秒) | 是 | 在成片时间线上的出场时刻 |
| `source` | string | 是 | 素材来源。**走 assemble_edl 分段拼接时 source 必须是已渲染的分段 MP4**（如 `片段/a.mp4` / 录屏切片 `录屏/a.mp4`）；`.html`（hyperframes 章节）**仅用于纯 hyperframes 单段渲染路径**，不进 assemble_edl（先由所选渲染器产出 MP4 再入 EDL）|
| `source_in` | float(秒) | 是 | 从 source 的第几秒开始取 |
| `source_out` | float(秒) | 是 | 取到 source 的第几秒（须 > source_in）；本路径不变速，源区间长度必须等于 timeline 区间长度|
| `section` | string | 建议 | 所属章节：`intro` / `body` / `outro` 或具体章节名（按当前 brief 或既有剪辑说明选填）|
| `voiceover` | string | 建议 | 该 scene 对应的口播句（人眼对照用，不参与机检）|
| `word_ts` | float[] 或 null | 否 | 该 scene 内自己的口播词级时间戳（秒）；为空则回退 `metadata.word_ts`。**取代上游 beats 字段**，落地 「词到」轴 |

> 字段语义转译表（上游 → 本协议）：`source_file → source`、`lyric → voiceover`、
> `beats → word_ts`、`section` 保留、`timeline_start/timeline_end/source_in/source_out` 保留。
> 音乐拍点不是本 EDL 的必需输入；本协议只验证显式提供的锚点。

---

## 机检（`validate_edl.py`）

| # | 校验 | 函数 | 失败意味着 |
|---|---|---|---|
| ① | 时间线连续 | `check_contiguity` | scene 之间有空洞/重叠（黑场或画面叠帧）|
| ② | 顺序非递减 | `check_source_ordering` | 同 source 倒带（素材回放往回跳）|
| ③ | source 区间 | `check_source_validity` | `source_out <= source_in`（零长/反向切片）|
| ④ | 覆盖整片 | `check_coverage` | 末尾 scene 没盖满 `total_duration`（结尾断片）|
| ⑤ | 精确去重 | `check_no_repeats` | 同 `(source, source_in)` 重复（同一帧素材用两次）|
| ⑥ | 区间重叠 | `check_source_overlaps` | 同 source 两段 `[in,out)` 重叠（观众看到重复画面），O(n log n) 排序扫描 |
| ⑦ | 卡点对齐 | `check_wordts_alignment` | scene 切换没卡在 `word_ts` 容差内（默认 30ms，允许提前 2 帧预入场）-- **「词到」失配** |
| ⑧ | head-buffer | `check_head_buffer` | `source_in` 距素材头 < 3 帧 -- 现役 validator 的保守头部缓冲约束；是否出现闪帧须看实际解码与成片，不能由此推定必然发生|

另有⑨ source 实体存在性检查：传入 EDL 路径后按该目录解析素材。①②需要 `timeline_*`；缺 `total_duration` 时覆盖项记 skipped，装配模式则拒绝；缺可信 `word_ts` 时不做词级对齐，不能把空结果当已验证。源与 timeline 等长、实际媒体范围/尺寸/音轨等由 `assemble_edl.py` 继续检查。

---

## 最小合法示例

```json
{
  "metadata": {
    "total_duration": 6.0,
    "fps": 30.0
  },
  "audio_mode": "source",
  "output_file": "成片.mp4",
  "scenes": [
    {
      "n": 1,
      "timeline_start": 0.0,
      "timeline_end": 2.0,
      "source": "片段/a.mp4",
      "source_in": 0.5,
      "source_out": 2.5,
      "section": "intro"
    },
    {
      "n": 2,
      "timeline_start": 2.0,
      "timeline_end": 4.0,
      "source": "片段/b.mp4",
      "source_in": 0.5,
      "source_out": 2.5,
      "section": "body"
    },
    {
      "n": 3,
      "timeline_start": 4.0,
      "timeline_end": 6.0,
      "source": "片段/c.mp4",
      "source_in": 0.5,
      "source_out": 2.5,
      "section": "outro"
    }
  ]
}
```

先做纯结构校验：读取以上 JSON 调用 `validate_edl(edl)`，预期 `8/8 checks passed`，其中词级项因缺数据不执行实际对齐，source 存在性列为 skipped。这不证明示例素材存在或已经听审。

实际工程将 JSON 保存到项目目录，提供三个各至少 2.5 秒、尺寸一致且带原声的 MP4，再运行 `python3 scripts/validate_edl.py <项目>/edl.json` 检查实体。每段源区间 `2.5−0.5=2.0s`，分别匹配时间线 `0–2 / 2–4 / 4–6`，累计 6 秒；不虚构 `word_ts`。

声音意图必须明确：`source` 保留源声、`silent` 明确静音，两者均不得残留 `audio_file`；`external` 才提供 `audio_file` 或 CLI `--audio`，它会替换源声，不会自动混音。
---

## 怎么接出片管线

### 1. 既有媒体剪辑

```text
brief 或既有剪辑说明 → 检查素材 → 写 edl.json
  → validate_edl.py <项目>/edl.json
  → assemble_edl.py <项目>/edl.json --out <新的成片路径>.mp4
  → 实际成片技术检查与完整视听审查 → 修改后重新审查
```

录屏、真人口播、已有 B-roll 和已渲染代码片段都可直接作为 MP4 source。统一帧率、画布与声音意图按工程声明；异尺寸素材需同时明确 `--width/--height`。不要求先转文章、网页或 HyperFrames 工程。需要代码动画时才调用所选引擎；EDL 不接收 HTML。

### 2. 节奏与视觉审查

依据 brief 判断信息密度、镜头变化、字幕可读性和配乐关系，可参考 [scene-mix-rule.md](visual-craft.md)。不由 `section` 字段推出固定组件数量、明暗配额或 scene 时长跨度；该字段不参与这里的配比机检。

### 3. 可选的词级对齐

实际取得并验证词级时间戳时，第⑦项按 `word_ts` 检查切换容差（默认 30ms，允许提前 2 帧）。保留转录/对齐来源供复核；不指定必须使用某个转录模型或引擎。只有块级锚或子句估时时，省略 `word_ts`，不得改称词级 verified。没有词级锚不阻塞既有媒体编辑；其他视觉和节拍审查按所选方案进行。

---

## API / 程序化校验

```python
from scripts.validate_edl import validate_edl, assert_valid_edl

result = validate_edl(edl)            # 返回 {"passed", "errors", "skipped", "summary"}
if not result["passed"]:
    ...                               # 自查 result["errors"][check_name] 列表

assert_valid_edl(edl)                 # 不过直接抛 AssertionError（CI / 出片脚本卡门）
```

可选覆盖参数：`word_ts=` / `total_duration=` / `fps=` / `align_tolerance_ms=`（默认 30）/
`early_frames=`（默认 2）/ `head_buffer_frames=`（默认 3）。

测试：`pytest tests/test_edl_validation.py -v`（覆盖各项通过/失败，以当前测试为准）。
