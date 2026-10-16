# 来源、采用与能力边界

本项目把多项参考的制作方法合并到单一流程；并不把安装这些上游当成默认执行链。

| 参考 | 采用内容 | 处理 |
|---|---|---|
| [showheyohtaki/motion-prompt](https://github.com/showheyohtaki/motion-prompt) | 动效／镜头术语、spec、纯时间 Canvas 代码和按需检索 | 原 CLI 最小捆绑，固定 770eefb7091cc725ab0eb6d4ef5cbf28b28e282c；MIT，目录和选中条目按需获取，保留单一制作入口 |
| [Kianzzz/xilo-opus-video](https://github.com/Kianzzz/xilo-opus-video) | 制作说明、动态验证、连续镜头、时间驱动、音画事件、混音、局部迭代与交付 | 方法适配；参考提交 f2cd828e2692e7186186408ee01a936707c2c38d，不捆绑原版导演 |
| [lemomo-ai/lemo-opuscar](https://github.com/lemomo-ai/lemo-opuscar) | 空间连续性、手绘推理、印刷材质和风格一致性 | 方法转述，不复制 43 风格库或安装器 |
| [Vincentwei1021/mg-styles-15](https://github.com/Vincentwei1021/mg-styles-15) | 图形变化、节奏与音画 cue | 方法转述 |
| [chuspeeism/dashi-animationstyle](https://github.com/chuspeeism/dashi-animationstyle) | 中文词句锚点和字幕／动作关系 | 方法转述，不把估时包装成对齐 |
| [alchaincyf/huashu-art-motion](https://github.com/alchaincyf/huashu-art-motion) | 大场景、构图和合成思路 | 方法转述，不承诺未验证的透明渲染 |
| [WaterDJiang/Wattter_openSkills](https://github.com/WaterDJiang/Wattter_openSkills) | 工程版本、素材与渲染关联、帧检查 | 复用本项目单套机制 |
| [Vincentwei1021/video-shotcraft](https://github.com/Vincentwei1021/video-shotcraft) | 镜头卡、构图、衔接和可编辑性 | 合并流程，不新建工作台 |

来源未确认的 archival-doc 未安装、未捆绑、未计入能力。借鉴方法不代表逐项复制上游代码或已达到其成片质量。

## 工具与许可

HyperFrames 作为独立安装的运行依赖，不捆绑其包和字体、音乐等素材。实际版本和许可见依赖清单。`validate_edl.py` 衍生自 guigulaoshi/music-video-director-skill（MIT）；`normalize_loudness.py` 和 `check_merge_compat.py` 的借鉴来源及修改记录保留在文件头。完整许可见仓根第三方说明。

本包提供编导工作法和真实工具，不是任意内容一键大片生成器。确定性检查仅覆盖抽样时刻；工程检查不替代视听判断。没有自带付费 TTS、生成视频、复杂 3D 或自动上传实现。使用宿主额外工具时按其实际授权和输入输出验证，不因提示词写了能力就宣称已完成。
