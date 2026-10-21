# 生产事件与工具

## 同一时间来源

已有工程沿用其唯一 timeline，不为了本工具复制第二份时间线。新作可使用 examples/timeline.json 的事件形状。镜头覆盖全片、共享切点从同一个值复用，事件不能越出镜头；requires_audio 必须明确。timing_basis 取 authored／estimated／verified_audio，只有经过实际证据导入的旁白块才用最后一种。

```sh
python3 "$SKILL/scripts/production_timeline.py" export "$PROJECT/timeline.json" "$PROJECT/derived" \
  --dependency "$PROJECT/index.html" --dependency "$PROJECT/node_modules/gsap/dist/gsap.min.js"
python3 "$SKILL/scripts/production_timeline.py" check "$PROJECT/derived/production-build.json"
```

实际字体、脚本、素材和生成器都应加入 dependency，不由导出器猜测。导出 events.js、字幕 JSON／SRT、sound-cues.json 和 motion-review-plan.json；画面从 window.productionTimeline.events 取时序。声音事件给真实消费方，不因导出 JSON 就声称声音已经入片。

导出器拒绝空／缺失依赖，记录源与产物 hash。改事件或依赖后使用 --refresh 重新导出，不能手改派生数据。production-build 证明当前字节一致，渲染和审片另有证据。

案例采用记在原制作说明，原文与来源回执留在 references。实际改写的代码、字体和媒体才进入运行依赖；未执行的提示词、检索索引不绑定影片渲染。只改推荐标签不应使旧片过期；实际时间源、采用素材或实现字节变化则必须重建对应消费者与证据。

## 场景声音决定与旧工程迁移

在原 timeline 的 `sound_design` 中按既有镜头 ID 记录决定。每个镜头恰好覆盖一次，相同决定可合并 `scene_ids`，时间仍只取 shots/events，不另写一份。以下是字段示意，填入当前工程真实 ID 后使用：

```json
"sound_design": [
  {"scene_ids": ["seaside"], "mode": "source", "reason": "原声海浪与脚步已能交代空间，保留它们。", "source_elements": ["native-seaside"]},
  {"scene_ids": ["explanation"], "mode": "supplement", "reason": "为讲解补一条平稳底乐，讲话时避让。"},
  {"scene_ids": ["answer"], "mode": "quiet", "reason": "只留对白，让观众听清这句答案。"}
]
```

`source` 需真实 `<audio>`／`<video>` 元素 ID，文件在项目内且列入构建依赖；元素明确 `data-start`、`data-duration`，有效音量大于零、未 muted，并实际覆盖相应镜头。已有剪裁用 `data-media-start`／`data-playback-start`；这个检查适配器不接受原声变速，先生成有来源记录的派生媒体。`supplement` 每个所列镜头需有原 events 中的正音量 `sound` 事件，可保留 `source_elements`；它们由下一节接线。`quiet` 指有意不加这些场景声音，允许对白继续；整个作品无声才设 `requires_audio: false`。不要为过检查把未决场景批量写成 quiet。

兼容边界：旧事件文件仍可 export/check；**有声 HTML 工程重新运行 `render_production.py render` 前必须补此决定**。空数组、漏镜头、虚假的补音或缺原声元素均拒绝。旧无声作品仍支持 `requires_audio: false`。这是渲染前置契约变化，迁移时由 Agent 依据原声与制作说明补决定，不能自动推断“只有对白就已设计好”。

HTML 渲染器在启动编码前和编码后调用 `production_sound.preflight`，复核当前 cue 与实际自动音轨、锁定字节、有效增益及原声依赖，结果记入原 render receipt 的 `verification.sound_wiring`，状态仅为 `wired_not_listened`。原生片段、Remotion、自有 FFmpeg/EDL 装配器在其真实消费者实现等价核对，保留现有字段与引擎；本 HTML 检查不替它们宣称通过，也不将检查 JSON 当成最终音频听审。

## 显式音效接线

新音效按 [资源配置](assets-and-profile.md) 保留适用的项目声音、查询显式启用的精选库；在线缺件的搜索、许可与下载执行 [Openverse 音效](openverse-sfx.md)。采用的声音必须先成为项目内真实音频与素材锁条目，再由下述工具消费；远程链接不直接挂入最终工程。

使用 `generate_sfx_tags.py index.html --manifest assets.lock.json --cues derived/sound-cues.json` 先只读检查；明确加 `--apply` 才修改自动标记区域，不覆盖手写音轨。最小素材锁的 items 条目包含 id、revision、scene_id、project_path 和实际 sha256，路径相对锁文件，必须能在工程内安全引用。每个 cue 显式给实际素材身份、全片秒值和时长；工具核对字节与真实音频长度，不会只凭素材同名就自动配声。

cue 仅接受 `id`、`asset_id`、`revision`、`scene_id`、`time`、`duration`、`volume`、`track`；未知字段会报错，不能假定 `media_start` 或 `playback_rate` 已被执行。`time` 是音频文件开始播放的全片时间，不一定是文件内动作点。需裁切或变速时先在项目内生成派生音频，保存父素材 hash、处理命令及来源回执，实测新时长并更新素材锁；原批准试听不自动覆盖改过的音色。

内部声音标记在源文件第 `m` 秒、裁切入点为 `a`、速度倍率为 `r` 时，其新位置为 `(m-a)/r`；要对齐画面第 `T` 秒，cue 起点为 `T-(m-a)/r`。标记必须在保留源区间内，起点不得为负，尾音仍须落在镜头许可范围。标记的含义要有实际依据，信号峰值不自动等于听到的起音；连续环境音不硬填冲击标记。

应用后将修改过的 HTML、`assets.lock.json` 和实际音频纳入 dependency，重新导出构建再渲染。计划 cue 未接入、被改时点/音量/轨道、缺文件、错版本或未绑定依赖时，通用渲染入口会在编码前拒绝；只运行 take 或导出 cue 不算入片。旁白／背景音乐是单独的真实媒体，不能拿一个提示音代替完整声音制作。

## 真实旁白

production_narration.py import --record 原制作记录.json --audio narration.wav --out evidence.json 导入已存在的分块制作记录，并重新探测音频长度、SHA、全文及块边界；不会生成 TTS 或自动强制对齐。check 子命令重验。

timeline 可引用 narration: {"evidence":"evidence.json","offset":0}。verified_audio 事件必须对应真实完整块及 narration_block 索引；拆字幕的插值标为 estimated，不冒称字级精确。最终配音通过项目已有工具取得，未授权新服务不自动启用。

角色对话与多机位沿同一条项目时间线：记录实际音源、源区间及入片位置，切机位可继续引用同一对白，不另建声音时间表。按现有消费者支持的字段表达；本工具的旁白块证据不自动提供多人声道识别、逐词对齐或口型验证。对白音轨改动后，重新核对受影响的口型、字幕和切点，并刷新相关派生证据；未变化部分沿用原证据。

修改旁白文本、语速或音频字节后，先刷新对应制作记录和真实块证据，再重导出受影响时间事件、字幕、语义动作与避让区间。导入器会核对音频、制作记录和块证据，构建检查会拒绝已绑定输入的变化；新导出不能自动证明旧人物画面已匹配新声音。若用音频驱动口型，在原镜头请求／来源记录里绑定实际驱动音频及区间，由该生成或装配消费者核对；没有此检查时如实保留待复核状态，不把新 timeline 的通过扩展为口型已通过。只换配乐且旁白不变时，不因此重生人物或重配对白。

## 声音与字幕

字幕保留专有词和完整语义；不缺字、错断或叠行。强调与动作从同一事件取时间。已有 SRT 可以直接用，不强迫迁移协议。

mix_production_audio.py 将已有旁白与音乐装配进视频，讲话区间、gain、attack／release 和 offset 显式提供，音乐不足长不自动循环。原片有声默认拒绝；用 --source-audio preserve 或 replace 明确选择。提供有效父渲染回执时可生成绑定输入的派生回执。

```sh
python3 "$SKILL/scripts/mix_production_audio.py" \
  --video "$PROJECT/renders/high.mp4" --narration "$PROJECT/assets/narration.wav" \
  --music "$PROJECT/assets/music.wav" --intervals "$PROJECT/speech-intervals.json" \
  --source-audio replace --output "$PROJECT/renders/mixed.mp4"
```

真实讲话区间不得冒称逐词发声检测。最终试听和必要响度处理见媒体编辑。

后续 FFmpeg 混音才加入的声音，以该步骤的实际命令、源区间、EDL 和回执为准，不假填成 HTML 已入轨。最终消费者须核对计划声部是否真的被混入、原声是否保留及各声部电平；仅探测到一个音频流或整片 LUFS 达标不能证明配乐/环境声存在。素材批准、接线检查和最终混音试听分别记录。

整混音相似也不能单独证明每个保留声部都存在：较强配乐可能掩盖很弱原声被删除。以信号核对保留原声时，由实际装配器依据对应处理链的分轨或参考混音，核查编码前与实际编码后的原声贡献，并验证“保留配乐、删除或静音目标原声”的反例能被拒绝。算法与阈值限于已验证的适配器，不复制单片数值；无法可靠分辨时标明未验证，留待相应复核，不能用整混音通过代替声部完整性。

## 确定性与审查绑定

```sh
python3 "$SKILL/scripts/check_timeline_seek.py" "$PROJECT/index.html" \
  --times 0,0.5,1 --size 1280x720 --root root --browser "$BROWSER" --out "$PROJECT/qa/seek-v1"
```

使用 Playwright，检查顺序、逆序及冷 context 截图、资源、字体和页面错误。不要把返回 GSAP thenable 的 pause／seek 直接交给 Playwright 等待。采样一致不证明全片所有帧和声音。

final-review.json 在真实审查后记录 approved、output_sha256、production_build_sha256 和 render_receipt_sha256。render_production.py check-review --project ... --output ... --review ... 只验证这份记录仍对应当前输入输出，不自动创造人工认可。

## 本机可选调度

默认命令直接运行。明确设置 SANSHENG_VIDEO_COMMAND_PREFIX 时，值为非空 JSON argv 数组，作为命令前缀传递参数；不进行 shell 求值。它供已有本机队列适配，公开用户无需配置。包装器必须保留参数和退出码，不能在内外重复抢同一名额。
