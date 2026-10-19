# 按镜头取用动效与音效

## 什么时候触发

在镜头设计阶段，先确定观众要看到什么变化。需要图形变形、揭示、层次视差、镜头移动或转场，且项目没有合适现成实现时，查 Motion Prompt。明确说出库名、编号或参考链接时直接取相应条目。纯剪切、静态阅读、已有合适动作的局部修改可以跳过。

声音独立判断：动作确实需要触感、空间或情绪反馈时，按 [资源配置](assets-and-profile.md) 保留适用的项目声音、查询显式启用的精选库，缺件再查 Openverse。动效不自动附带音效；持续运动也不必持续发声。需要安静、旁白密集或会分散注意时留白。

镜头记录沿用现有说明，增加必要的选用理由、动效编号／来源版本／修改说明、音效资产 ID。不要另造第二套镜头时间表。

## 快速检索和获取

`SKILL` 指本 Skill 目录，`PROJECT` 指当前视频工程。Motion Prompt 入口需要 Node >=18，无 npm 安装；音效工具使用 Python 标准库和已安装的 ffprobe。

```sh
# 把中文意图转换成 2–4 个英文检索词；上游原生支持英／日文，没有中文语义检索。
node "$SKILL/scripts/motion_prompt.mjs" search mask reveal --pack motion --limit 3
node "$SKILL/scripts/motion_prompt.mjs" search push zoom --pack camera --limit 3
# 只取决定采用的条目；单次上限 8，通常一个镜头只需 1–2 个。
node "$SKILL/scripts/motion_prompt.mjs" get 005 --out "$PROJECT/references/motion-005"
node "$SKILL/scripts/motion_prompt.mjs" kit motion --out "$PROJECT/references/motion-005"
# 诊断来源与缓存
node "$SKILL/scripts/motion_prompt.mjs" info

# 搜索少量声音候选并保存原 API 结果，再核来源页、试听选择。
python3 "$SKILL/scripts/openverse_audio.py" search 'soft click' --out "$PROJECT/references/click-search.json"
python3 "$SKILL/scripts/openverse_audio.py" fetch \
  --record "$PROJECT/references/click-search.json" --id SELECTED_ID \
  --output "$PROJECT/hf/assets/sfx/click.mp3"
```

上游动效共 5 包、120 条（本次固定版本）。优先 `motion`（动态图形）和 `camera`（镜头／转场）。`ui`、`lp` 仅在视频真的演示界面或网页时采用；`photo` 是摄影外观参考，不能承诺为视频直接套滤镜。图库适合查看动态样例；用户明确想自己选时才运行 `pick --timeout 60`，不把人工挑选作为自动制作的必经等待。

动效入口复用原作者 CLI，代码与数据默认固定到 `770eefb7091cc725ab0eb6d4ef5cbf28b28e282c`。首次只下载约 320 KB 目录，随后按需取条目和每包一份 kit，不全仓克隆、不抓全图库。目录缓存 6 小时，条目按数据版本缓存；缓存可供断网复用，首取失败如实报错。`MOTION_PROMPT_BASE` 可显式指定本地 API 副本或其他来源；项目必须记录实际来源，不能将覆盖后的数据冒称默认固定版本。原 CLI 的 `--out` 可覆盖同名文件，修订时使用新目录。

音效搜索缓存 6 小时，媒体按 URL 缓存，输出到工程时检测文件和音频时长并写 `.source.json`，已有输出拒绝覆盖。缓存目录可用 `--cache` 指定；缓存只是加速，实际采用文件仍须保留在项目。API 遇 403／Cloudflare 时不反复撞接口：直接在浏览器打开报错提供的 API URL，将结果 JSON 保存后交给同一 `fetch`。下载失败可检查原站预览或改选，不自动采购或登录。工具不代替原站许可复核、试听和 CC BY 对外署名，完整规范见 [Openverse 音效](openverse-sfx.md)。

## 接入原有制作链

1. **镜头设计**：按表达问题检索，选机制而非叠效果；读选中条目的 spec、代码和 kit。记录库 ID、commit、取回代码 hash 与实际采用后的 hash，保留 MIT 作者声明和完整许可。
2. **真实时间**：有旁白先测旁白，动效起止、停留和声音 cue 都从唯一生产 timeline 的镜头／事件取得。素材录音开头可能有静音，先测声音起点再剪取；“文件从这里播放”不等于“点击声在这里发生”。
3. **制作**：在现有 HF／Canvas／SVG／GSAP 镜头中重建。上游是卡片演示代码，颜色、字体、尺寸和业务文案应适配项目。各包 kit 必须分作用域；按条目自身尺寸和周期绘制再缩放。不要整段搬运演示中的浏览器外壳、自动光标或多次循环到无关影片。
4. **时间驱动**：上游 `cells[i](ctx,w,h,u)` 为纯时间函数。视频中用镜头相对时间驱动，单次入场只播放一次，需要延长就延长停留，不无意循环。HF 适配遵循 [现有运行契约](hyperframes.md)，不以 RAF／墙上时钟驱动离线渲染。生成式视频可采用对应镜头术语作提示，不能承诺按代码参数精确生成。
5. **声音入片**：下载回执的 hash、实际项目路径加入原 `assets.lock.json`，来源并入项目来源表；声音事件仍用 `production_timeline.py export` 导出，交给 `generate_sfx_tags.py` 或原 FFmpeg／EDL 消费者。不要手填第二套 cue，缓存命中也不免除素材锁检查。
6. **验收与修订**：检查起态、峰值动作、稳定期和接缝，新增代码做顺序／逆序／冷启动相同时刻取帧。听实际成片中的同步、人声遮挡与峰值。更换动作只修相关镜头，更换声音只改对应资产与事件，再重建受影响输出。

## 价值与边界

Motion Prompt 的价值在共同术语、可核查参数和可逐帧执行的参考代码，最适合减少“描述不清—盲试效果”的时间。它不是成片素材下载站，也不替代导演、现有渲染器或混音器。保留单一 video 入口，无需安装上游另一套 Skill。

[组合实测](../examples/motion-sfx/README.md)用界面演示这个合适场景取 `#085 Ripple effect`，配真实 CC0 点击声，经同一 timeline 输出 MP4；这是代码／素材取用和 FFmpeg 装配验证。没有凭此声称已验证 HF 渲染或整部业务影片的审美与听感。
