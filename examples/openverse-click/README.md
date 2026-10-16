# 真实 Openverse 点击音验证

2026-10-17 实测。播放 [demo.mp4](demo.mp4)：5 秒短片，第 1 秒开始播放鼠标点击素材，蓝色方块标示声音所在的时间区间。原音见 [mouse-click.mp3](assets/mouse-click.mp3)。这是接口与入片验证，不是审美示范。

素材：[Mouse click sounds](https://freesound.org/people/Masgame/sounds/347544/)，作者 [Masgame](https://freesound.org/people/Masgame/)，[CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/)。来源页确认包含单击、双击与中键点击。文件从 Openverse 返回的公开 HQ MP3 预览 URL 下载，58,080 字节、实测 2.310385 秒、44.1kHz 双声道；并非需要原站登录才能下载的原件。

过程与证据：

1. Chrome 直接打开 `https://api.openverse.org/v1/audio/?q=click&license=cc0,by&page_size=3`，返回 240 条结果，取首条 CC0 素材。终端同一 API 请求遇到 Cloudflare 1010，浏览器可正常返回 JSON。
2. 打开原始来源页确认作品、作者与许可，下载返回的媒体 `url`。`sources.json` 与 `assets.lock.json` 记录来源、下载变体及字节 hash。
3. `production_timeline.py export` 从 `timeline.json` 生成 `sound-cues.json`，`generate_sfx_tags.py --apply` 实际校验音频、hash 和时间边界，并将音轨写入 `index.html`。
4. FFmpeg 读取导出 cue 的时间、时长与音量，将同一真实 MP3 延迟 1 秒、以 0.5 音量加入短片，输出 H.264/AAC MP4。本例没有运行 HyperFrames 渲染。
5. 对最终 MP4 完整解码，并将解码音轨与源音在 cue 位置比较：相关系数 `0.997926`，cue 前峰值 `0`，声音段有实际信号。详情见 `validation.json`。这证明实际音频已入片；不证明已完成主观试听、音色或成片审美验收。

同一时间源重新导出／检查 HTML 接线：

```sh
python3 "$SKILL/scripts/production_timeline.py" export timeline.json derived \
  --dependency index.html --dependency assets/mouse-click.mp3
python3 "$SKILL/scripts/generate_sfx_tags.py" index.html \
  --manifest assets.lock.json --cues derived/sound-cues.json
```

示例未对原 MP3 做破坏性修改；成片对音量做 0.5 倍缩放并转码为 AAC。项目路径均相对本目录。`index.html` 仅用于接线验证，蓝色方块由 FFmpeg 测试画面生成。
