# 真实媒体编辑

生成视频的原声取舍、环境声连续性及事件拟音见 [生成片段的视听设计](generated-audiovisual.md)。检查最终音轨中实际保留的声音；轨道或事件存在，不代表已进入成片或已完成听审。

保留现有工程、字幕与真实原声。先 ffprobe 实测，不用文件名推断画幅、声道或起点。口播／录屏可通过宿主已有 auto-editor 或场景切分工具处理，但本包不额外安装第二套编辑技能。

EDL 使用现有 scenes 协议，示例见 examples/edl.json；对应完整字段说明见 references/edl-schema.md。顺序执行：

```sh
python3 "$SKILL/scripts/validate_edl.py" "$PROJECT/edl.json"
python3 "$SKILL/scripts/check_merge_compat.py" --from-edl "$PROJECT/edl.json"
python3 "$SKILL/scripts/assemble_edl.py" "$PROJECT/edl.json" --audio-mode source --out "$PROJECT/edited.mp4"
```

source 保留分段原声，silent 明确去声，外部 --audio 会替换原音。外部音轨明显长短不符拒绝，不用 shortest 掩盖截断；混音走独立显式操作。对不同画幅、声道、非零起点先作明确处理。只检查 EDL 引用的素材，不遍历整个库。

局部修订时保留不受影响的源与音轨，检查修改边界和最终总时长；最终完整解码，不能只看字幕文件正确。

normalize_loudness.py 支持 --lufs、--lra、--out，目标取项目交付要求。代码中的平台快捷值是经验预设，不是平台最新强制标准。处理会改变音轨，必须试听最终版本；需要严格双遍响度时按实际测量与 FFmpeg 工具能力执行，不把一次滤镜处理当作精确达标证明。

录屏交付前检查账号、通知、令牌和个人资料。遮罩必须覆盖实际出现时间与区域；不能把没完整检查过的录屏标记为脱敏通过。
