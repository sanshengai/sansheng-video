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

没有 delivery.json 的既有视频可由发布器接收显式文件清单；不能为了适配本导出器伪造解码或作者接受记录。字幕尚未由本导出入口自动带入，需在发布清单中明确声明并核对文件。平台时长、尺寸、标题、字幕与审核规则由发布端查当前要求并验证；导出成功不等于上传通过。
