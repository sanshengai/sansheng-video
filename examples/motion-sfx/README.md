# 动效与真实音效组合验证

播放 [demo.mp4](demo.mp4)：4.8 秒界面演示，0.7 秒、2.9 秒两次点击，波纹与真实单击音从同一个 `timeline.json` 事件触发。采用 Motion Prompt `#085 Ripple effect`，仅因本例确实演示按钮反馈而选用 LP 包；普通视频优先 motion／camera 包。

动效来自 Shohei Ohtaki 的 [Motion Prompt](https://github.com/showheyohtaki/motion-prompt/tree/770eefb7091cc725ab0eb6d4ef5cbf28b28e282c)，固定提交 `770eefb7091cc725ab0eb6d4ef5cbf28b28e282c`，MIT。`kit-lp.js` 原样保留；`ripple.js` 保留作者声明，改为中文文案并从导出的生产事件读取点击时间／位置，光标轨迹时间随事件计算。页面将强调色改为蓝色。完整 MIT 许可位于 `../../scripts/vendor/motion-prompt/LICENSE`。来源及改前／改后 hash 见 `sources.json`。

声音来自 [Masgame / Mouse click sounds](https://freesound.org/people/Masgame/sounds/347544/)，CC0 1.0。音效下载工具重新取回公开 HQ MP3，字节 hash 与上一轮真实样本一致。原录音不是从点击瞬态开始：本例提取 0.93–1.13 秒（检测到首次点击起音约 0.931 秒），开头 2 ms、结尾 5 ms 淡化，保存为 WAV。两次使用同一素材，不把包含多次点击的整段录音分别叠到两个动作上。音效技术探测与原站来源核验见前一例 `../openverse-click/`。

从本例所在目录重建到新输出名：

```sh
python3 render.py --output /path/to/new-demo.mp4
```

使用已安装的 Python Playwright Chromium 和 FFmpeg；缺依赖时按仓内固定开发依赖准备，不临时安装 latest。脚本在临时目录从唯一 timeline 导出 `events.js` 和声音 cue，调用真实 `generate_sfx_tags.py --apply` 检查素材锁并接线，再逐帧求值 Canvas、用 FFmpeg 消费相同 cue 混入音频。临时导出回执按机器重建，不把绝对路径回执当可移植输入。

验证覆盖：5 个时刻直接／倒序／冷启动帧一致；144 帧实际渲染；最终 MP4 完整解码；两处解码音轨与源单击片段相关性；源文件与输出 hash。结果见 `demo.validation.json`。使用 Canvas + FFmpeg，没有运行 HyperFrames，未以此证明 HF 渲染适配已实测。主观试听仍待验；技术通过不代表整部业务影片已达到成片质量。

本机一次检索实测：冷缓存搜索约 1.18 秒，同查询缓存命中约 0.054 秒；取 #085 约 0.91 秒，取 LP kit 约 0.74 秒。只下载目录、所选条目和一个 kit，非全库。记录见 `retrieval-benchmark.json`，不作为网络速度承诺。

本轮新工具实测中，终端 Openverse 搜索返回 240 条结果，选中的同一 CC0 音频下载 hash 与既有样本一致；此前浏览器回退仍作为接口被拦时的备选。两次入片音频与源片段相关系数均约 0.9999。
