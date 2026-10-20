# 配音：选型与实际时间线

新建旁白、设计角色对话或用户要求换配音时读对应小节。已有真人声、角色声和栏目声线沿原工程；不因新装模型重配。

## 角色对话的表演

先确定每个轮次的人物意图与对方反应，再写台词、语气、重音、停顿和接话位置。让停顿承担犹豫、理解或回应，不用均匀句间空白代替表演；抢话只在内容需要且不妨碍理解时使用。声线及语速范围沿角色约定，换机位不自动重选供应商或声线。

需要固定对白节奏与精确口型时，按 [生成镜头](generated-shots.md#对白与视频输入) 核实音频驱动能力。支持时先确定对白音轨，再生成对应表演和覆盖机位；原生音画路径则把这些表演意图落实到实际请求，生成后检查对白，不额外强制合成一套 TTS。保留已经合适的原声。

核对白内容与可听辨度后，记录实际采用的音轨和片段边界，再组织切镜。需要逐词字幕或精细切点时另取实际转写／强制对齐证据；时间戳表示定位，不证明语气自然、口型正确或毫秒级准确。听相邻轮次及整段，检查说话人、声线、停顿、接话和听者反应。

## 采用结论

**VoxCPM2 为本机中文／通用旁白的首选候选，Kokoro 为英文短句、试剪的轻量备用。** 不是十套同时运行，也没有完成十库音质盲测。首次新声线先出短试听；确认声音后固定控制词、参考声、模型版本，按句／语义块批量合成。用户已给出声音方向且允许候选制作时自行生成，不新增必经审批。

| 项目 | 官方实现与适用性 | 本流程决定 |
|---|---|---|
| [VoxCPM2](https://github.com/OpenBMB/VoxCPM) | 中文、多语、指令式音色设计与参考声；代码和模型 Apache-2.0；官方实现支持 MPS | 主选；本机实际生成通过，音质仍需试听 |
| [Kokoro](https://github.com/hexgrad/kokoro) | 82M 固定声线，多语；模型 Apache-2.0，24kHz，官方有 MPS 用法 | 英文／预览备用；不以轻量模型替代既定角色 |
| [Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS) | Base、CustomVoice、VoiceDesign 是不同模型；Apache-2.0；官方示例主要 CUDA，Mac MLX 是另一实现 | 后备评估，当前不再安装第二套大模型 |
| [IndexTTS](https://github.com/index-tts/index-tts) | 情绪、时长等表演控制；模型自定义许可须单独核 | 特定角色表演有需求再接，非默认 |
| [CosyVoice](https://github.com/FunAudioLLM/CosyVoice) | 多语／方言，服务化工具链；Apache-2.0 | 有常驻服务需求再考虑 |
| [GPT-SoVITS](https://github.com/RVC-Boss/GPT-SoVITS) | 短样本克隆、声音微调；MIT 代码，模型与声音权利另核 | 训练角色声音的专项工具，不逐片训练 |
| [Chatterbox](https://github.com/resemble-ai/chatterbox) | 多语、MPS 示例、音频水印；MIT | 有明确跨语声线需求再比较，不同时常驻 |
| [Fish Speech](https://github.com/fishaudio/fish-speech) | 当前代码和模型有社区许可及商业／托管条件 | 保持暂不启用；不自动接付费 API |
| [SoulX-Podcast](https://github.com/Soul-AILab/SoulX-Podcast) | 长篇多人播客、轮次与方言，Linux 工具链 | 多人播客立项时再考虑 |
| [VibeVoice](https://github.com/microsoft/VibeVoice) | Realtime 与长篇模型、ASR 是不同任务；Realtime 以英语为主 | 当前离线中文视频无必要，不把 ASR 当 TTS |

模型许可不代替参考声音的使用权。克隆只接受已获授权的声源，并在 manifest 写明 `reference_rights`；不使用样片角色声音冒充自己的角色。

## 调用与接入

安装在隔离 Python 3.12 环境：`uv venv --python 3.12 /path/to/tts-venv`，然后 `uv pip install --python /path/to/tts-venv/bin/python voxcpm==2.0.3 kokoro==0.9.4`。不改系统 Python。首次使用模型显式加 `--allow-download`，之后默认只用本机缓存。两模型 revision 固定在脚本内；升级先独立验证。Kokoro 英文前端还需要 spaCy 的英语模型，准备环境时显式安装，不能把首次下载时间当推理速度：

```sh
uv pip install --python /path/to/tts-venv/bin/python https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl
```

```sh
/path/to/tts-venv/bin/python scripts/synthesize_narration.py examples/tts/voxcpm2.json --out PROJECT/voice-v1 --allow-download
/path/to/tts-venv/bin/python scripts/synthesize_narration.py examples/tts/kokoro.json --out PROJECT/preview-v1 --allow-download
```

manifest 的 `blocks` 是明确语义块，空输入和过长块会拒绝。模型一次加载；首段生成后作为后续段的参考声以减少音色漂移，仍需听相邻段。输出单块 WAV、连续 `narration.wav`、带模型／参数／哈希／真实块边界的 `production.json`，并通过现有 `production_narration.import_evidence` 生成 `narration-evidence.json`。随后用原生产事件编译时间线，不再凭字数估整片时长。块边界是真实样本计时，**不是逐词对齐**；要逐词高亮，另取得可靠对齐结果。

不覆盖输出目录。改词后新版本重新生成受影响段并重新装配、导入证据；当前适配器每次运行会生成 manifest 中全部段，不宣称已有跨运行的逐段缓存。模型缓存可复用，工程只保留用到的音频。最终混音仍执行原声音事件、避让和响度流程。

## 验收边界

本机 Apple Silicon M5 Pro 24GB：VoxCPM 2.0.3 + 固定 VoxCPM2 revision 的 MPS 路径实测成功；首次载入约 12 秒，一段 5.92 秒音频生成约 9.7 秒。两个独立段的完整适配器输出 6.08 秒连续音频并成功导入现有旁白证据。此数字仅代表该短样本的技术表现，不代表长片速度、逐字正确或音质认可。PyPI 2.0.3 没有 main 文档里的 `seed` 参数，适配器使用 torch RNG；不直接照抄 main 接口。

Kokoro 0.9.4 的完整适配器也已实际输出 2.35 秒英文音频，导入旁白证据并编译时间线通过；同样尚未听审。

机器检查非空音频、样本数、解码、哈希及边界；`listening_status` 始终先为 pending。正式入片听完整音轨，核漏字、多语读音、停顿和声线；ASR 回听校稿有条件再加，不能把生成成功写成吐字全对。
