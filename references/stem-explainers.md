# 数理推导与图解动画

适用于数学、物理等需要精确几何比例、函数坐标系、公式分步变形与物理量联动的讲解视频。仍沿用唯一执行底座（HyperFrames 0.8.72 + GSAP 3.14.2 + `timeline.json`），不另装 Manim、Remotion 或第二套补间引擎。

## 四个核心机制

| 教学表达问题 | 机制 | 实现方式 |
|---|---|---|
| 图动了但读数忘改、直角变歪 | **单变量同源求值** | 几何顶点、度量标注和公式实时读数由同一个纯函数 `renderAtTime(t)` 计算，禁止图形和数字各写一套独立补间 |
| 公式硬切难看清来龙去脉 | **项级锚点变形** | 用 `stem_kit.py formula` 给关键项打 `{term_id#role:expr}` 锚点，移项跨等号时沿弧线平移并切换正负号，不整行闪烁替换 |
| 代数符号和图形对不上号 | **色彩代数绑定** | 同一变量或面积块在公式、图形和标注中锁死同一语义色（如 `role="a"` 青绿、`b` 琥珀、`c` 深靛），底色保持干净克制 |
| 动点轨迹在离线 seek 时错乱 | **预采样弧长路径** | 轨迹预先用 `svg_curve(..., traced=True)` 生成带 `pathLength="1000"` 的 `<path>`，用 `strokeDashoffset` 从 `1000 → 0` 揭示，不在回调里累积数组 |

## 工具与出片前验算

`SKILL` 指本 Skill 目录，`PROJECT` 指当前视频工程。`scripts/stem_kit.py` 仅依赖 Python 标准库：

```sh
# 1. 导出离线公式样式与确定性时钟辅助脚本（纳入构建依赖）
python3 "$SKILL/scripts/stem_kit.py" emit-assets "$PROJECT/assets/stem"

# 2. 编译带项级锚点的离线公式 HTML（支持 \frac、\sqrt、上下标与常用符号，未知命令直接报错）
python3 "$SKILL/scripts/stem_kit.py" formula '{lhs:3x} {move#b:+ 5} = {rhs:17}' --id eq-step1

# 3. 出片前必跑数理事实与安全区闸门（有理数精确检验，不等价变形或越界直接返回 1）
python3 "$SKILL/scripts/stem_kit.py" verify "$PROJECT/stem-spec.json"
```

在生成脚本中也可直接 `import stem_kit` 调用确定性 SVG 原语：

- `Plane2D.create(domain_x, domain_y, viewport, canvas=[w, h], equal_aspect=True)`：将数学笛卡尔坐标（`+y` 向上）映射为 SVG 像素坐标（`+y` 向下）。默认校验竖版 `1080×1920` 安全区 `x: 120–940, y: 250–1500` 与横版 `1920×1080` 四周 `≥96 px`；几何作图必须保持 `equal_aspect=True`，防止横竖换版把圆压成椭圆、把直角压成钝角。
- `svg_axes` / `svg_curve` / `svg_polygon` / `svg_right_angle` / `svg_dimension_segment` / `svg_vector_arrow`：生成平面直角坐标系、函数曲线、多边形、正交校验直角框（非直角顶点直接报错拒绝）、平行度量线及按模长成比例的物理矢量箭头。手写白板草图笔画仍可用 `scripts/geometry_strokes.py`。

## HyperFrames 离线求值防坑

- **严禁把动态状态挂在根时间线的 `gsap.timeline({ onUpdate })` 上**：HyperFrames 渲染时调用单参数 `tl.seek(ts)`，GSAP 默认 `suppressEvents=true` 会跳过根时间线回调，导致数字读数与动态图形在成片里全程冻结。动态求值一律使用 `StemRuntime.bindClock(tl, duration, renderAtTime)`（内部以全片线性子补间的 `onUpdate` 驱动，`tl.seek(ts)` 正向、逆向、冷启动均必触发）。
- **`renderAtTime(t)` 必须是 `t` 的纯函数**：不读取上一帧 DOM 文本累加，不使用 `Math.random()` 或 `Date.now()`；可变画面属性集中由 `bindClock` 一次性赋值，SVG 图元位移旋转优先写原生 `transform="translate(...) rotate(...)"` 属性、HTML 浮动项写 `left/top/opacity`，避免与额外的 CSS `transform`／`will-change` 补间混用导致 Chromium 冷启动与顺序 seek 之间产生合成层 1 像素抗锯齿差异。修改后必须通过 `check_timeline_seek.py` 的正向／逆向／冷启动同帧哈希核验。
- **把生成的 `stem-math.css`、`stem-runtime.js` 和 `stem-spec.json` 纳入工程记录**：渲染所用的样式与脚本一并传给 `production_timeline.py export --dependency`，避免改了公式样式却复用旧构建回执。

## 横竖双画幅与认知节奏

- **横竖同源、分别构图**：同一份 `stem-spec.json` 与 `timeline.json` 事件可同时驱动竖版与横版，但几何舞台按画幅分别给 `viewport`（竖版常采用上图形舞台 + 下公式推导区；横版常采用左图形舞台 + 右公式推导区），绝不把竖版画面整体拉伸或硬裁成横版。
- **每步变形留够认知停留**：代数移项、合并同类项、系数化为 1 或几何割补落定后，在时间线 `reads` 中声明公式与关键结论的稳定停留窗口（完整显现后至少停留 `1.5–2.2 s`，长式按[数字默认值](craft-defaults.md)公式顺延），不连续快切式子让观众追赶。
- **主持角色服务推导焦点**：复杂几何辅助线生长或多步公式变形期间，主持角色退为画外音或角落静帧，不在图形与公式正上方做大幅肢体动作；抛出问题与收束结论时再回主画面（衔接规则见[知识解释与系列表达](knowledge-explainers.md)）。
