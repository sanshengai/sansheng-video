# 把成片交给发布器

`scripts/export_publish.py` 消费 `package_delivery.py` 产生的 `delivery.json`，核对实际成片/封面哈希及原有完整解码证据。接受状态须绑定作者实际反馈，不能由导出器替作者填写。此处只处理数据交接，不制作视频、不上传。

```sh
python3 scripts/export_publish.py /path/delivery/delivery.json --targets /path/targets.json --output /path/publish-manifest.json
```

targets.json 包含显式 targets 数组，例如：

```json
{"targets":[{"id":"douyin-main","platform":"douyin","account":"main","content_type":"video","endpoint":"draft","title":"本条标题","text":"本条说明 #话题"}]}
```

每个平台使用自己的文案/终点；省略标题和说明时沿用交付稿，绝不自动选择账号或公开发布。输出 schema_version=1，与文章发布器使用同一份中性合同。覆盖不同版本会拒绝，改稿使用新输出路径。

交付规格可选声明 `"subtitles":[{"path":"captions.srt","language":"zh-CN"}]`。打包器复制所选 SRT/VTT 并锁定哈希，发布导出器将回执中的字幕带入每个目标；不扫描目录猜版本。同语种多份字幕须先确定最终版本。平台是否支持独立字幕、支持哪种格式由发布端核实；不支持时明确说明，不能静默丢弃，也不擅自重渲烧录。

没有 delivery.json 的既有视频可由发布器接收显式文件清单；不能为了适配本导出器伪造解码或作者接受记录。平台时长、尺寸、标题、字幕与审核规则由发布端查当前要求并验证；导出成功不等于上传通过。
