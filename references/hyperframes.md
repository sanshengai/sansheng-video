# HyperFrames 执行

默认只使用一个内部执行层，不再运行另一个导演的意图采访、全局安装器或自动技能更新。已有工程保持其锁版本；下列工具适配 HyperFrames 0.8.72、30fps。代码镜头与 24 fps 生成片段混用时，交付帧率按[帧率规则](craft-defaults.md#帧率)统一。

## 依赖与工程

在工程内显式安装并保留锁文件：

```sh
npm init -y
npm install --save-exact hyperframes@0.8.72 gsap@3.14.2
```

浏览器由使用方准备，提供真实可执行文件路径。缺依赖时先诊断，不能用裸 npx 随机下载 latest。CLI 使用已安装包的 `bin/hyperframes.mjs`，通过其 `--help` 核对命令；不要用较新文档中的 API 猜旧版本。

新项目保留明确的 `<html><head>...</head><body>...</body></html>`。独立页面的 composition root 直接在 body 内，不套 template。根声明 composition id、data-width、data-height、data-duration，样式按根尺寸布局；不要出现第二个被静态扫描误识别的 composition root。可执行模板或预览文件放扫描范围外，不能让字符串里的 root 被当作第二工程。

使用 GSAP 时注册一个 paused timeline 到 `window.__timelines[id]`，id 与 root 一致，初始化完成后才注册。根 duration 与生产时间一致。CSS 初始 transform 不与 GSAP 同属性争用；使用 fromTo 或明确设置起态。字体、媒体和本地脚本准备完成后再渲染，避免远程资源临时失效。

所有状态由视频时间决定。固定随机种子；不使用 Date.now、后台计时器或异步副作用推进内容。不要把 Xilo render(t) 循环直接嵌入 HF 控制循环。音视频媒体按该锁版本的真实契约交给框架调度，不在逐帧求值中调用 play()。

## 实际命令

先导出生产事件并绑定 index.html 和所有真实运行依赖，再执行：

```sh
python3 "$SKILL/scripts/render_production.py" render \
  --project "$PROJECT" --source "$PROJECT/timeline.json" \
  --runtime "$PROJECT/node_modules/hyperframes" --browser "$BROWSER" \
  --output "$PROJECT/renders/draft.mp4" --quality draft
python3 "$SKILL/scripts/render_production.py" check "$PROJECT/renders/draft.render.json"
```

`--quality high` 用于最终文件，另起输出名；已有文件需明确 --refresh 才覆盖。适配器核对构建、运行包、浏览器和最终媒体，保留真实日志与回执。它不自动安装依赖，不证明人已看过或听过。

- **批量 SVG／纯矢量板开渲前先过真实 Chromium DOM/SVG 几何预检**：多集图表动画不能仅靠源码正则检查（正则无法算出字体实际渲染宽度与多行折行）。在送入 HyperFrames 逐帧渲染前，须在 headless Chromium 里 `document.fonts.ready` 后把 timeline seek 到终态，调用 `getBBox()` 与 `getBoundingClientRect()` 校验：① `.topbar` `.hdr-lockup` 与 `.era-pill` 不碰车；② `.stage` 不溢出 810px 安全区；③ `<svg>` 内文本不裁出 `viewBox` 或溢出所属圆角框；④ `<text>` 之间、未遮罩 `<line>`/`<polygon>` 与文字之间无碰撞（先修 spec 再渲染）：

```sh
node "$SKILL/scripts/audit_svg_dom_layout.mjs" --html "$PROJECT/hf_plates_dir"
node "$SKILL/scripts/audit_svg_dom_layout.mjs" --self-test
```

跨机器恢复需要重新建立本机路径和构建／渲染回执；绝对路径回执不是可移植工程格式。保留相对资源、源文件和 package-lock 后在新环境重建，而非直接把旧回执当新机器证据。

更复杂的 HF API 先查已安装包及其对应官方技术资料，技术层按需加载；没有这类技能时不要求另装一套总控。
