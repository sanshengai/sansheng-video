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

## 显式音效接线

使用 `generate_sfx_tags.py index.html --manifest assets.lock.json --cues derived/sound-cues.json` 先只读检查；明确加 `--apply` 才修改自动标记区域，不覆盖手写音轨。最小素材锁的 items 条目包含 id、revision、scene_id、project_path 和实际 sha256，路径相对锁文件，必须能在工程内安全引用。每个 cue 显式给实际素材身份、全片秒值和时长；工具核对字节与真实音频长度，不会只凭素材同名就自动配声。

应用后将修改过的 HTML 和音频纳入 dependency，重新导出构建再渲染。旁白／背景音乐是单独的真实媒体，不能拿音效 cue 代替完整声音制作。

## 真实旁白

production_narration.py import --record 原制作记录.json --audio narration.wav --out evidence.json 导入已存在的分块制作记录，并重新探测音频长度、SHA、全文及块边界；不会生成 TTS 或自动强制对齐。check 子命令重验。

timeline 可引用 narration: {"evidence":"evidence.json","offset":0}。verified_audio 事件必须对应真实完整块及 narration_block 索引；拆字幕的插值标为 estimated，不冒称字级精确。最终配音通过项目已有工具取得，未授权新服务不自动启用。

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

## 确定性与审查绑定

```sh
python3 "$SKILL/scripts/check_timeline_seek.py" "$PROJECT/index.html" \
  --times 0,0.5,1 --size 1280x720 --root root --browser "$BROWSER" --out "$PROJECT/qa/seek-v1"
```

使用 Playwright，检查顺序、逆序及冷 context 截图、资源、字体和页面错误。不要把返回 GSAP thenable 的 pause／seek 直接交给 Playwright 等待。采样一致不证明全片所有帧和声音。

final-review.json 在真实审查后记录 approved、output_sha256、production_build_sha256 和 render_receipt_sha256。render_production.py check-review --project ... --output ... --review ... 只验证这份记录仍对应当前输入输出，不自动创造人工认可。

## 本机可选调度

默认命令直接运行。明确设置 SANSHENG_VIDEO_COMMAND_PREFIX 时，值为非空 JSON argv 数组，作为命令前缀传递参数；不进行 shell 求值。它供已有本机队列适配，公开用户无需配置。包装器必须保留参数和退出码，不能在内外重复抢同一名额。
