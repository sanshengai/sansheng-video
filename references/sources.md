# 来源、采用与能力边界

本项目把多项参考的制作方法合并到单一流程；并不把安装这些上游当成默认执行链。

| 参考 | 采用内容 | 处理 |
|---|---|---|
| [观默的制作讲解](https://x.com/guanmo_ai/status/2112525216924807210)、[Gorden 的北京解说](https://x.com/Gorden_Sun/status/2112488511479902346)、[Miao 的系列讲解](https://x.com/WaterrrMiao/status/2112122511509065797) | 贯穿对象、多媒介的空间主线、逐步建立关系、主持人进退与标题阅读过程 | 作者说明、抽帧和局部时序观察转为可选知识解释方法；未据此声明完整视听或本地成片复现通过，不捆绑视频、音乐和未公开代码 |
| [nakazakifam 的多机位对话制作说明](https://x.com/nakazakifam/status/2104231262600700140) | 同一段讲话的机位覆盖、对白与镜头装配分工 | 方法转述；五机位是作者此前案例，不是数量要求，不证明本包已接入其模型或复现成片 |
| [yihui-dev/awesome-opus5-5-videos](https://github.com/yihui-dev/awesome-opus5-5-videos) | 精选案例的段落组织、对象连续和声音编排描述 | 固定 92aee2f586ac0715cb3cbcb6384834f98a33383d；8 条自写摘要与本地检索，原文选中才取，不捆绑视频、完整提示词或第二生产入口；视听和复现分别标记 |
| [showheyohtaki/motion-prompt](https://github.com/showheyohtaki/motion-prompt) | 动效／镜头术语、spec、纯时间 Canvas 代码和按需检索 | 原 CLI 最小捆绑，固定 770eefb7091cc725ab0eb6d4ef5cbf28b28e282c；MIT，目录和选中条目按需获取，保留单一制作入口 |
| [Kianzzz/xilo-opus-video](https://github.com/Kianzzz/xilo-opus-video) | 制作说明、动态验证、连续镜头、时间驱动、音画事件、混音、局部迭代与交付 | 方法适配；参考提交 f2cd828e2692e7186186408ee01a936707c2c38d，不捆绑原版导演 |
| [lemomo-ai/lemo-opuscar](https://github.com/lemomo-ai/lemo-opuscar) | 51种风格的用途/表达/音画机制、98条电影语法、绘制与镜头实现 | 源码取回固定d33bdea74eeecde3922b0fbad227f0d3dc7afe75，机制研究b5e8ef93930b6d828f352055a689320f138237b1；本地有界search/inspect，选中源码按SHA256缓存；不安装第二生产总控 |
| [Vincentwei1021/mg-styles-15](https://github.com/Vincentwei1021/mg-styles-15) | 图形变化、节奏与音画 cue | 方法转述 |
| [chuspeeism/dashi-animationstyle](https://github.com/chuspeeism/dashi-animationstyle) | 中文词句锚点和字幕／动作关系 | 方法转述，不把估时包装成对齐 |
| [alchaincyf/huashu-motion](https://github.com/alchaincyf/huashu-motion) | 真实产品研究、信息形状、视觉性格、关键画面、原生声音/修订与经验回流 | 固定5f2608c2e12abcf518f74dde86093b19f7f88603；形成按需宣传片方法，本地原生工具实际试制；未捆绑运行器或采样，未把技术验绿当视听认可 |
| [alchaincyf/huashu-art-motion](https://github.com/alchaincyf/huashu-art-motion) | 大场景、构图、风格语言与故事母题分离、跨场景验证和正面经验 | 固定8a0d7d72ca65fcce6f8ba82c4a6c8dfe35b8422c；方法转述，与huashu-motion分别研究；不承诺未验证的透明渲染 |
| [WaterDJiang/Wattter_openSkills](https://github.com/WaterDJiang/Wattter_openSkills) | 工程版本、素材与渲染关联、帧检查 | 复用本项目单套机制 |
| [Vincentwei1021/video-shotcraft](https://github.com/Vincentwei1021/video-shotcraft) | 镜头卡、构图、衔接和可编辑性 | 合并流程，不新建工作台 |

来源未确认的 archival-doc 未安装、未捆绑、未计入能力。借鉴方法不代表逐项复制上游代码或已达到其成片质量。

## 工具与许可

HyperFrames 作为独立安装的运行依赖，不捆绑其包和字体、音乐等素材。实际版本和许可见依赖清单。`validate_edl.py` 衍生自 guigulaoshi/music-video-director-skill（MIT）；`normalize_loudness.py` 和 `check_merge_compat.py` 的借鉴来源及修改记录保留在文件头。完整许可见仓根第三方说明。

本包提供编导工作法和真实工具，不是任意内容一键大片生成器。确定性检查仅覆盖抽样时刻；工程检查不替代视听判断。本地 TTS 是可选依赖，付费服务、生成视频、复杂 3D 与上传仍需额外工具与实际授权。使用宿主额外工具时按其实际授权和输入输出验证，不因提示词写了能力就宣称已完成。
