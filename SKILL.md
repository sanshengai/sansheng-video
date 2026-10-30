---
name: sansheng-video
description: 当用户要制作或修改视频时使用：产品宣传片、文章／课程／知识讲解转视频、代码动画、AI 生成镜头短片、真人口播与录屏剪辑，以及配音、配乐音效、字幕、封面和成片交付；已有工程按差异继续。只研究他人成片不启动制作；静态配图与发布交给对应技能。
metadata:
  author: sanshengai
  version: "2.5.0"
  compatibility: Python >=3.10, Node >=22, FFmpeg and HyperFrames 0.8.72; Playwright for browser checks; numpy and Pillow for delivery QA
---

# Video · 单入口视频制作

负责从内容到可编辑成片的制作。默认用 HyperFrames 执行代码镜头，FFmpeg／EDL 处理真实媒体和声音。参考过的方法已合并在内部，不再启动另一个导演，也不让用户选择框架。

## 每次先做

1. 在 Skill 根运行 `python3 setup.py --show-profile`。新会话、接手旧工程、局部修改都要执行。返回配置时，读其中的 `context_file`；涉及素材且配置了 `media_library` 时，再读它的 `usage`。配置里的相对路径（`context_file`、`usage`、`tool` 等）一律以返回的 `root` 为根，不在本 Skill 目录下找。没有配置时，用项目自选的中性视觉，不套作者品牌。
2. 判断任务类型，决定从哪里进入：

| 任务 | 从哪里进入 | 先写什么 |
|---|---|---|
| 新作或整体重做 | 阶段 1 | 制作单（`new`） |
| 续作，或在已认可样板上扩片 | 阶段 1 | 制作单（`continue`），先列已认可组合 |
| 一次交付多条的系列或批量 | 阶段 1 | 制作单（`series`），再按[系列与批量扩展](references/production.md#系列与批量扩展) |
| 已有工程局部修改 | 受影响的阶段 | [修订卡](references/production.md#修订卡)；沿用原引擎、内容和约定，不重选风格 |
| 只处理素材、声音或字幕 | 对应阶段 | 不启动全链 |
| 已有口播、录屏或 B-roll | [媒体编辑](references/media-editing.md) | 先检查实际素材，不补写文章 |

3. 运行本包的相对路径脚本时，每次显式以 Skill 根为工作目录；终端不一定保留上次的 `cd`。

内容的事实裁决不归本 Skill：已有文章可直接转视频，课程、角色和栏目规范由输入方提供。项目约定、作者偏好和其他 Skill 的借调关系以 profile 的 `context_file` 为准。

## 阶段

| 阶段 | 交出什么 | 进入下一步的条件 | 读哪份 |
|---|---|---|---|
| 1 制作单 | `brief.md`，按[制作单模板](references/brief-template.md) | `check_brief.py` 无缺项；核心主张、结构或牵动全片的视觉方向已有作者判断，或作者已授权 Agent 自行决定（选择写进「自主决定」） | [制作流程 §1](references/production.md#1-内容变成影片) |
| 2 镜头与素材声音 | 每镜 ID、目的、变化和声音决定；素材候选与缺件 | 每个镜头都有可取得的画面和声音决定；要补的声音已取定素材，缺件就停在这一步并在制作单写明缺什么 | [§2](references/production.md#2-镜头设计) |
| 3 时间源 | `timeline.json` 或 EDL；真实旁白块 | `production_timeline.py validate` 通过（不写文件，制作时再 export／check）；`check_readability.py` 的提示已处理或写了理由 | [§3](references/production.md#3-按声音角色确定真实时间)、[生产事件与工具](references/events-and-tools.md) |
| 4 风险片段验证 | 覆盖最不确定处的一段连续片段 | 开篇、关键交接和音乐成立；已验证的方向和局部任务跳过此步 | [§4](references/production.md#4-制作与修订) |
| 5 全片制作 | 成片与渲染回执 | 计划的声音全部入轨；全片能连续播放 | [§4](references/production.md#4-制作与修订) |
| 6 测量与独立评审 | `qa/summary.md`、三张联系表、评审意见 | 响度达标；P0 已修，最多再修一轮复查 | [§5](references/production.md#5-检查和交付)、[独立评审](references/independent-review.md) |
| 7 听审与交付 | 交付目录、交付报告 | 下面的交付清单逐条有证据 | [§5](references/production.md#交付报告) |

阶段之间可以围绕高风险片段回看；回退范围由实际依赖决定，见制作流程 §4。

## 交付清单

局部修改：1、2、8、9、12 必做，其余只核对这次改动牵涉的项，未牵涉的沿用上一版证据。

| # | 检查 | 证据 |
|---|---|---|
| 1 | 最终文件完整解码，画幅、帧率、时长、音轨与制作单一致 | ffprobe／渲染回执 |
| 2 | 成片响度在平台目标 ±1 LU 内，真峰值 ≤ −1 dBTP | `qa_delivery.py` |
| 3 | 首帧是完整构图；面向发布的片子有封面 | 首帧截图、封面文件 |
| 4 | 竖屏信息流（profile 的 `delivery.feed_platforms`）开头 3 秒：评审只看 0–3 秒联系表就能说出这片讲什么，或制作单已写豁免理由；说不出时记 P1，修好或在交付报告说明 | 评审意见 |
| 5 | 讲解类片子的术语已说出并显示 | 字幕／画面文字 |
| 6 | 最长句、字幕读速、手机安全区没有未处理的提示 | `check_readability.py`、手机尺寸联系表 |
| 7 | 计划的声音全部入轨 | 渲染回执的 `sound_wiring` 或装配器回执 |
| 8 | 听审状态如实，没试听的标「待验」 | 最终验收记录 |
| 9 | 续作或扩片：已认可组合逐项对照过，修改范围外的画面没变 | 对照图、`compare_frames.py` |
| 10 | 系列：全部目标影片的开头和结尾横向一致 | 横向联系表 |
| 11 | 许可与署名齐全；录屏已脱敏 | 来源表、`ATTRIBUTION.md` |
| 12 | 交付报告已写 | 交付报告 |

## 铁律

- 不编造事实、数据、亲身经历、界面状态或 AI 回复；生成画面不冒充真实证据，模拟窗口标为示意。
- 不自动安装 latest、不调用付费生成服务、不上传、不发布；制作授权不等于发布或付费授权。生成图像、TTS、搜索等使用宿主已有且获授权的工具，其他 API 不伪装已提供。缺组件时明说缺什么，不偷换供应商，也不降为静态卡片冒充完成。
- 机器检查只证明技术项。完整播放、音色、叙事和审美要靠真实视听；没试听就标「待验」，可以先交候选；不代填人工批准，不用自评分代替作者认可。
- 时间只有一个来源：`timeline.json` 或 EDL。改了时间数据就重建它的消费者，不手改派生产物；修订用新输出名，保留旧版本。
- 声音随场景决定：保留够用的原声、补合适的素材，或有意留白；空计划不算决定。拟采用的声音必须进入音轨并检查最终混音，但不要求每镜都加音效。
- 录屏交付前检查账号、通知、令牌和个人资料。音效遇到 NC、ND、SA 许可不直接入片，CC BY 必须署名。
- 系列交付前，横向检查全部目标影片；批量出片前，对全部目标影片 × 全部画幅先跑一遍不出片的版式检查。
- 已有决定持续有效，「不重复确认」指不重复问作者，不等于不再对照：扩片和续作仍要逐项对照已认可组合。普通构图、目录和实现细节自行完成，不交回作者。

## 按需资料

**阶段 1**　必读[制作单模板](references/brief-template.md)和[数字默认值与套路清单](references/craft-defaults.md)。宣传片读[宣传片方法](references/promotion-film.md)，从作品目录选材读[真实作品选材](references/promotion-selection.md)，介绍真实网页读[真实网页介绍](references/web-walkthrough.md)；知识、城市／历史、角色系列读[知识解释与系列表达](references/knowledge-explainers.md)；面向发布的片子同时考虑[封面与首帧](references/video-covers.md)。

**阶段 2**　镜头、空间、材质与运动读[视觉机制](references/visual-craft.md)；新作定风格、找绘制或镜头实现查 [Lemo 风格与实现](references/lemo-opuscar.md)；段落组织、对象连续或音画编排卡住时查[视频案例参考](references/opus-video-cases.md)；动效术语、代码与配声读[动效与音效](references/motion-and-sound.md)。素材、品牌与许可读[资源配置](references/assets-and-profile.md)，音效缺件走 [Openverse 音效](references/openverse-sfx.md)，真实 B-roll 缺件走[在线画面素材](references/stock-footage.md)。

**生成镜头**　角色表演与连续片段读[生成镜头](references/generated-shots.md)，角色对话或口型同时读[配音的对话表演](references/tts.md#角色对话的表演)；追求大片感的逐镜叙事短片读[电影感生成短片](references/cinematic-generated-film.md)（生成前三道关卡）；写发给生成器的逐镜请求用[镜头请求模板](references/shot-request-template.md)；经 Muse 编排读 [Muse 结构化交接](references/muse-handoff.md)；光照、色彩、空间声音，以及配乐和音效该原生生成还是后期做，读[生成片段的视听设计](references/generated-audiovisual.md)。

**阶段 3**　必读[生产事件与工具](references/events-and-tools.md)；新增配音读 [TTS 选型与制作](references/tts.md)；真实媒体按场景剪辑用 [EDL 结构](references/edl-schema.md)。

**阶段 4–5**　新 HTML 镜头和渲染读 [HyperFrames 执行](references/hyperframes.md)，依项目锁核实际 CLI help；裁剪、装配、原声与响度读[媒体编辑](references/media-editing.md)；横竖版或保留已认可部分做局部修订读[多画幅与局部反馈](references/multi-aspect-revisions.md)；宣传片卖点证据与品牌原件预览读[证据与交付工具](references/promotion-evidence.md)。

**阶段 6–7**　评审按[独立评审](references/independent-review.md)；已接受的本地交付交给 `sansheng-distribute` 时读[发布交接](references/publish-handoff.md)，不重新渲染，也不要求写作技能介入；能力边界和借鉴来源见[来源与采用](references/sources.md)。
