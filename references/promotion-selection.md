# 从真实作品选材并进入镜头

目录是候选来源，不是审美结论。优先读取现有生图工具导出的 `sample-catalog/1`，没有该工具时可接项目同结构目录；不复制整库到视频 Skill，不依赖某个品牌的私有路径。

## 有限候选 → 看图 → 素材锁

```bash
python3 scripts/select_assets.py sheet project/catalog.json project/contact.png --aspect 3:4 --limit 24
python3 scripts/select_assets.py sheet project/catalog.json project/ppt.png --purpose PPT --limit 12
```

可选 `--group <已登记关系ID>`。总览默认最多 24 张，上限 48，侧车 JSON 将编号对应到完整 ID、用途、题材和状态。用途过滤不把合同“可用于 PPT”当作这张图已经是 PPT。没有结果时放宽条件或补真实作品，不能给空缺编用途。Agent 实际查看总览，放大关键原图逐字检查内容；竖版先找原生竖图，用途证据仍须能辨认完整封面／PPT／漫画。

选图文件：

```json
{"kind":"asset-selection/1","canvas":[1080,1920],"items":[
  {"asset_id":"目录中的稳定ID","fit":"contain","focal":[0.5,0.5]}
]}
```

`contain` 保留整图，`cover` 按焦点裁切；相同图需要重复出现时可写 `repeat_reason`。只有目录已支持的关系才填 `group`，不能用“同题对比”标签代替依据。

```bash
python3 scripts/select_assets.py lock project/catalog.json project/selection.json project/selection.lock.json
python3 scripts/selection_preview.py project/selection.lock.json project/selection-preview.mp4 --seconds 1.5
```

素材锁核对媒体与目录来源，提示上采样、明显裁切、重复、历史／待更新修订和未知使用范围；提示不是授权或自动准入。预览按顺序真实读取全部选图，保留原比例或明确裁切；每张 0.25–3 秒，总共最多 12 张、24 秒。它是检验选图、画幅与内容可读性的短预览，没有自动配乐，不冒充完成的宣传片。需要复杂镜头时沿既有 Lemo 或项目引擎消费同一素材锁，不更换现役渲染器。

## 接入现有制作时间源

在 `timeline.json` 可选加 `"asset_selection":"selection.lock.json"`，对应视觉事件的 `visual.asset_ids` 列出实际要展示的稳定素材 ID。每个选中 ID 均须有视觉事件；横竖版使用各自画幅的 selection，不把坐标直接复制过去。运行现有 `production_timeline.py export` 后，实际解析的素材写入 `events.js` 的 `asset_selection` 和 `asset-selection.json`，来源进入原有构建回执。

预览及时间线导出均会重新验证已选文件；删图、换图或修改来源后拒绝继续，不能用旧缓存假装构建成功。修改选图后新建锁与预览版本，确认实际画面随之变化。时间线导出本身只证明映射和输入有效；完整引擎仍须用这些文件绘制，并按最终成片核对入镜和审美。

选图顺序服务收益表达：不同用途接“能做什么”，受控画风组接“风格”，有依据的同构图色系组接“色彩”。题材相近但条件不同可做独立作品接力，不能称为同条件比较。片长与切换速度由观看价值和音乐段落决定，不用固定图片数量填满时间。
