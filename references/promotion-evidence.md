# 宣传片证据、品牌预览与交付工具

作品宣传（`showcase`）让观众记住可得到的成果；操作介绍（`walkthrough`）让观众完成任务；混合（`mixed`）声明主线 `primary`。片长、是否旁白、卖点数量由内容决定。先看作品、界面和原始能力，再定标题与承诺。每个短标题对应能说明它的画面：画风、用途和色系分别用各自证据，不让一个数量代替全部价值。

## 将收益和证据接入时间源

在现有 `timeline.json` 可选加 `"promotion": "brief.json"`，给展示该收益的事件加 `"claim_ids": ["multi-use"]`。原时间、镜头和声音字段保持原样。情绪镜头可以不引用卖点。Brief 最小结构：

```json
{
  "kind": "promotion-brief/1", "mode": "showcase",
  "audience": "需要文章配图的作者", "promise": "把内容变成可用的一组作品",
  "title": "让想法成为作品", "destination": "产品下载页",
  "claims": [{"id": "multi-use", "benefit": "同一主题覆盖不同用途", "evidence_ids": ["cover-series"]}],
  "evidence": [{"id": "cover-series", "file": "evidence/series.json",
    "sha256": "真实文件的 SHA256", "version": "核对的产品或样图修订", "acquired_at": "2026-01-01T00:00:00Z"}]
}
```

来源为网页时补 `url`，同时保留本地截图或操作记录，不能只留可能变化的 URL。路径相对 brief。证据指向实际素材或带素材指纹的原始登记；不能另写宣传词再把它当证明。同条件比较须有原请求／生成登记等依据；命名相似或题材相近只是候选，元数据不足就人工审查或改成普通作品展示。

```bash
python3 scripts/production_timeline.py export project/timeline.json project/derived
python3 scripts/production_timeline.py check project/derived/production-build.json
```

映射写进 `events.js` 的 `promotion` 和 `promotion-plan.json`，原证据及 brief 进入构建指纹。无镜头承接的卖点、未知 ID、缺失／变化的证据会被拒绝。渲染器仍须消费视觉事件和选材；导出只证明来源与镜头绑定，不证明事实正确、图已入镜或审美通过。整片编码前，先用实际素材预览最不确定的开篇、证据变化和音乐重音，内部迭代即可。

## 品牌原件与横竖屏预览

`brand_assets.py` 读取实际 profile.json。兼容旧 `brand.logo` / `logo_on_dark`；可选 `brand.variants` 区分完整标识和独立图形：

```json
{"brand": {"variants": {
  "full-dark": {"file": "brand/full-dark.png", "type": "full", "background": "dark", "roles": ["corner", "ending"]},
  "symbol-light": {"file": "brand/symbol-light.png", "type": "symbol", "background": "light", "roles": ["corner"]}
}}}
```

多项匹配时用 `--variant`；有 variants 却没有合适角色时不猜。不要把完整字标裁成图形冒充授权变体。预览可选依赖 Pillow，不调用就不新增核心安装要求。

```bash
python3 scripts/brand_assets.py profile/profile.json --background dark --role corner
python3 scripts/brand_assets.py profile/profile.json --preview project/logo-wide.png --canvas 1920 1080 --visible-width .15
python3 scripts/brand_assets.py profile/profile.json --preview project/logo-tall.png --canvas 1080 1920 --visible-width .20
```

宽度按 alpha 可见边界计算，保留原图颜色、比例和完整标识。辅助边框是设计留白，不能称为平台官方安全区；实际看对比度、遮挡和横竖屏大小。这些数值只是调用示例。现有引擎需要逐级缩放时在项目绘制适配中处理，不改第三方核心。

## 浅层交付

`package_delivery.py` 完整解码视频、复制实际文件、核对指纹、生成封面和本地预览。输入：

```json
{
  "video": "render/final.mp4", "filename": "Product-portrait-v2.mp4",
  "title": "产品竖版宣传片", "summary": "展示作品用途、画风与色系。",
  "suggested_title": "让想法成为作品", "project": "实际工程位置",
  "review_status": "candidate", "online_urls": []
}
```

`poster` 可给现有 JPG/PNG/WebP，否则从成片生成；`article_placement` 可补文章放置建议。已有用户认可用 `user_accepted` 并填 `review_source`，指明原话和适用版本。技术验收或旧版认可不能自动成为新片认可。

```bash
python3 scripts/package_delivery.py project/delivery-spec.json output/Product-portrait-v2
```

输出实际 MP4、封面、说明、JSON 回执和预览，可独立拖拽、播放、上传。不同内容拒绝覆盖，改用新版本目录；同输入重跑可复用同包。工程、旧稿留原位。私有 profile 决定交付根目录与 Finder 等本机操作。已有网站地址可以列出，无地址写未上传；工具不上传，微信等平台仍须自己的媒体上传流程。
