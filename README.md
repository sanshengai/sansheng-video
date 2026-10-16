# sansheng-video · 叁笙视频

**一个制作入口，把内容、镜头、动画、声音和可编辑交付连成一条线。**

[![MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE) [![Stars](https://img.shields.io/github/stars/sanshengai/sansheng-video)](https://github.com/sanshengai/sansheng-video) [![Release](https://img.shields.io/github/v/release/sanshengai/sansheng-video)](https://github.com/sanshengai/sansheng-video/releases)

中文说明在前，English guide 在文末。版本变化见 [CHANGELOG](CHANGELOG.md)。

## 能做什么

把已有文章、课程资料或视频需求整理为视频稿与镜头，默认用 HyperFrames 制作代码画面，FFmpeg／EDL 处理口播、录屏和声音。已有工程只改需要改的部分，不自动更换框架。

Xilo 等参考的制作方法已整合进内部流程，不用同时安装一排导演技能。品牌、内容规则和素材由项目或可选私有配置提供，公开核心没有固定作者水印。

| 输入 | 制作与交付 |
|---|---|
| 已有文章或课程 | 视频稿、镜头与运动设计、音画时间、MP4 和可编辑工程 |
| 口播、录屏、B-roll | 保留原声的剪辑、字幕与分段装配 |
| 已有工程和修改要求 | 局部修订、相关数据重建及当前版本检查 |

这是一套由 Agent 使用的制作技能与工具，不是任意内容一键生成大片的服务。影片审美仍需真实业务视听验收；本仓不宣称达到参考作者的成片质量。无自带付费 TTS、生成视频或上传 API。

## 看看工程产出

以下为中性协议示例，不是影片质量演示：

```text
project/
  brief.md              # 内容、受众、镜头和交付要求
  index.html            # 可编辑画面
  timeline.json         # 镜头、字幕、动作和声音事件
  assets/               # 实际采用素材
  sources.json          # 来源、许可和 hash
  package-lock.json     # 项目运行依赖
  derived/              # 导出事件、字幕和构建证据
  renders/              # MP4、日志和渲染回执
```

[时间线示例](examples/timeline.json)、[EDL 示例](examples/edl.json) 均为合成输入。示例不会自动替你生成业务镜头；Agent 根据内容制作画面。

## 安装：保留一份工作源

先将本仓 clone 到你自己的技能存放目录，再让宿主加载仓根 `SKILL.md`：

```sh
git clone https://github.com/sanshengai/sansheng-video.git
```

Codex 常见共享入口是 `~/.agents/skills/`；Claude Code 常见个人入口是 `~/.claude/skills/`。按实际宿主设置，将 `sansheng-video` 软链接到这一个 clone，不复制第二份。已有同名入口先检查，避免覆盖现有安装。

Claude Code 插件安装可使用本仓 marketplace：

```text
/plugin marketplace add sanshengai/sansheng-video
/plugin install sansheng-video@sansheng-video-marketplace
```

其他宿主只需能读取 Agent Skill 格式。不要求另装 Xilo 或 HyperFrames 导演总控。

### 运行依赖与快速开始

- Python >=3.10，Node >=22，FFmpeg／ffprobe。
- 在视频工程内显式安装：`npm install --save-exact hyperframes@0.8.72 gsap@3.14.2`，保留锁文件。
- 准备本机 Chromium／Chrome 可执行文件，不隐式下载浏览器。

```sh
python3 setup.py --check --runtime /path/to/project/node_modules/hyperframes --browser /path/to/browser
```

`ready` 表示依赖探测通过，不代表影片已经制作。把工程路径交给 Agent，例如：

> 把这篇已定稿文章做成 60 秒中文讲解视频。用对象关系和动作解释核心概念，保留真实出处，交 MP4 与可编辑工程；不要再给我展示样板。

具体执行命令见 [HyperFrames](references/hyperframes.md)、[事件与声音](references/events-and-tools.md)、[已有媒体](references/media-editing.md)。

本机可以建立被 Git 忽略的 `profile/` 目录或链接；`python3 setup.py --show-profile` 读取它。显式环境变量优先，未配置时返回 `null`。

### 可选配置

| 配置 | 能做什么／需要提供什么 | 不启用会怎样／如何启用 |
|---|---|---|
| 私有品牌与精品库 | 使用自己的 Logo、颜色、内容规则与素材目录 | 使用项目已有或中性配置；运行 `python3 setup.py` 指定私有 profile，或设置 `SANSHENG_VIDEO_PROFILE_DIR` |
| 浏览器确定性检查 | 比较顺序、逆序、冷启动帧；需要 Playwright | 不加载该检查器，不影响核心编辑；需要时安装 `playwright==1.62.0`，使用 `setup.py --check --browser-checks` |
| 既有本机调度 | 把编码命令交给已有本机资源队列 | 默认直接运行；高级使用者设置 `SANSHENG_VIDEO_COMMAND_PREFIX` 为 JSON argv 前缀 |

配置示例在 `.env.example` 和 `profile.example/profile.json`。本包不自动加载 shell 的 `.env`；明确加载后使用，配置里不写密钥。

### 更新与国内下载

在唯一 clone 内 `git pull --ff-only`，再查看 [Release notes](https://github.com/sanshengai/sansheng-video/releases)。可 Watch → Releases 订阅版本。网络不畅可从可信 GitHub 镜像下载同一 tag 的源码，核对版本与来源；不要把来历不明的二次包当官方版本。

## 检查与能力边界

核心工具有时间线、真实音频、剪辑和回执回归测试。干净环境测试与当前发布证据见 [验证说明](references/verification.md)。技术检查不替代完整播放和试听；估时字幕不等于逐词对齐。跨机器恢复需从源工程重新建立本机回执。

[借鉴来源](references/sources.md) 逐项说明采用范围；[第三方许可](THIRD_PARTY_NOTICES.md) 说明改编代码与运行依赖。不会复制参考视频中的音乐、字体或私有素材。

## 贡献与隐私

建议从真实影片问题出发提交修改。安装 `requirements-dev.txt` 后运行 `python3 -m pytest tests -q`，有真实媒体用例时先准备 FFmpeg。浏览器检查需要显式 Playwright 和浏览器。

贡献前运行 `git config core.hooksPath .githooks` 启用脱敏护栏。不要提交 `.env`、私有 profile、用户文章、项目回执或媒体缓存。安全问题请参阅 [SECURITY](SECURITY.md)。

## 关于作者 · About the author

我是叁笙，一个用 AI 做内容、也用 AI 造工具的人。这套技能来自真实工作流，清理私料后公开，欢迎按你的业务改进。

[网站](https://sanshengai.top) · [小宇宙](https://namecard.xiaoyuzhoufm.com/nnl8x) · [微博](https://weibo.com/u/7546221967) · [小红书](https://www.xiaohongshu.com/user/profile/5c716b6d000000001000f5c4) · [邮箱](mailto:sandypoli@gmail.com)

<img src="assets/qrcode-gongzhonghao.png" alt="微信公众号：叁笙早安AI" width="180">

## English guide

One production entry for article-to-video, code animation and real-media editing. The agent directs the film; HyperFrames renders authored HTML scenes, while FFmpeg handles cuts and explicit audio operations. Existing projects keep their engine. Xilo and other references inform the workflow, rather than adding parallel directors.

Clone this repository once and load its root SKILL.md in your agent host. Install Python 3.10+, Node 22+, FFmpeg, and project-local HyperFrames 0.8.72 / GSAP 3.14.2. Supply an explicit browser executable. Run `python3 setup.py --check --runtime ... --browser ...` before rendering. Brand profiles and browser checks are optional, described above and in the linked references.

Deliverables include editable sources, project dependencies, adopted-asset provenance and MP4 output. Technical checks never establish human audiovisual approval. No bundled paid generation, cloud credentials or upload service. See [credits](references/sources.md), [licenses](THIRD_PARTY_NOTICES.md), and [changes](CHANGELOG.md).

## License

Original code: MIT. Adapted Apache-2.0 portions retain their upstream terms; see THIRD_PARTY_NOTICES.md.
