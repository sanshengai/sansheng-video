# Openverse 音效：按镜头找，选中再入片

适用于新作、已有工程补音效和局部换音。音效包含动作声、环境声、提示与转场声；旁白和配乐仍沿现有制作方式。已有工程里合适且许可明确的声音继续用。需要新增声音时，默认按镜头需要检索 Openverse，不先翻本地大库或百度网盘。旧的本机集中库和网盘素材库已退出本流程，在线缺件时改关键词或保留留白。

已有可执行的搜索／下载入口与浏览器 JSON 回退，见 [动效与音效](motion-and-sound.md#快速检索和获取)。下载回执仅证明元数据和实际音频，不代替下面的来源、试听与入片步骤。

## 1. 从镜头写声音意图

在原镜头表／唯一 timeline 里记稳定 `scene_id`、声音目的、实际动作点、情绪、时长与人声避让。例如“纸页翻开后落稳，轻纸张摩擦，短而近，不盖住旁白”，比“高级转场”更能选到合适声音。先判定是否真的需要声音，不要求每镜都有。

已有剧情镜头若包含合适原声，先听原声，避免叠两套脚步、雨声或对白。不得为加音效替换角色音色。声音事件与字幕、动画共用全片时间；不另建独立计时表。

## 2. 小批在线检索

入口：[Openverse](https://openverse.org/)、[官方 API](https://api.openverse.org/v1/)。宿主有 HTTP／终端工具时可请求音频搜索接口；没有时通过浏览器选择 Audio 分类。无需为本流程默认注册账户、申请新权限或开通付费服务。

```sh
curl --fail --show-error --silent --get --max-time 30 \
  'https://api.openverse.org/v1/audio/' \
  --data-urlencode 'q=soft paper page turn' \
  --data-urlencode 'license=cc0,by' \
  --data-urlencode 'page_size=5'
```

先用准确的英文动作／材质／空间词，必要时补中文。每个声音需求先看 3–5 个候选，明显不合适再换一组词；不要批量翻页下载。`license=cc0,by` 是默认候选筛选，方便商业用途与剪辑；它不代替原始来源核验。不要凭历史记忆硬编码额度、时长单位或额外筛选参数，使用前可查当前官方接口文档。

Openverse 是索引，检索命中不等于文件一定可下。读取结果的 `id`、`title`、`creator`、`creator_url`、`license`、`license_version`、`license_url`、`foreign_landing_url` 和媒体 `url`；缺失字段如实留空，不推断作者或许可证。返回字段以实际响应为准。候选链接是来源证据，媒体地址才用于取文件。

403／超时先记录具体失败，可用宿主浏览器直接打开相同 API URL，或改走 Openverse 网页。2026-10-17 实测终端收到 Cloudflare 1010 时，Chrome 直接访问 API 能返回真实 JSON；网页应用资源报错不等于 API 也不可用。不得绕过安全警告或验证码。429 按响应的 `Retry-After` 等待，没给则稍后再试，不连续重试。原媒体链接失效时查来源页的合法下载入口或换候选，不以 HTML 页面冒充音频。在线入口仍不可用时，才使用项目已有或用户授权的其他在线来源素材；也可保留无音效候选，交付时说明。API 文档核对通过不等于当前机器已下载成功。

## 3. 核来源，试听后选定

打开 `foreign_landing_url` 核对当前作品、作者、许可版本、下载对象和额外条件。优先 CC0；CC BY 需要保留完整署名。遇到 NC、ND、SA 或额外限制，不按“免费可用”直接入片：另选许可适配的候选，已有明确授权则记录依据。CC0 同样保留来源。来源与索引冲突或证据不明时换候选。

试听候选的起音、尾音、底噪、空间感和是否包含不需要的音乐／对白，再在当前镜头与旁白一起比较。宿主无法听音时可以完成检索和候选下载，但状态必须是“待试听”，不能写成“最合适／已验收”。技术探测与波形不代替听审。

只下载选定的少量文件到项目 `assets/sfx/`，实际试音必须下载的候选放项目临时目录。下载后用 ffprobe 检查确有音频、格式与真实时长，再计算 SHA256；拒绝错误页和空文件。工程内使用本地文件，不在渲染时依赖远程 URL。若需裁切、淡入淡出或转码，保留来源证据，另写派生文件、处理说明和新 hash，不覆盖来源文件。

## 4. 接上已有素材锁与声音事件

把选定文件加入原项目 `assets.lock.json` 的 `items`，保留现有条目。每条包括 `id`、`revision`、`scene_id`、`project_path`、实际 `sha256`；路径相对锁文件。`id` 可用 `openverse-<媒体 id>`，revision 绑定此次文件字节。声音放在 HTML 入口目录内可引用的位置，例如 `hf/assets/sfx/`，对应锁路径为 `hf/assets/sfx/<file>`；根 HTML 则使用 `assets/sfx/`。

在项目 `sources.json`／现有来源表中保留 Openverse id、来源页、原媒体 URL、作者、许可证名与版本及链接、UTC 获取时间、本地路径、hash、使用场景和修改说明。对 CC BY 在项目 `ATTRIBUTION.md` 记作品名、作者／链接、来源／链接、许可／链接与修改说明，并安排到实际交付的片尾或发布说明；只有工程内部存一份不能冒称已完成对外署名。

在唯一 timeline 中用事件的 `scene_id` 与全片 `start`／`end`（秒）定位声音；`sound` 只写素材 `asset_id`、`revision`、`duration` 和 `volume`，不在其中重复写时间。确保 `requires_audio: true`，事件处于对应镜头内，素材锁身份与下面的值一致。示例是某个镜头中的事件，不是完整 timeline：

```json
{
  "id": "paper-turn",
  "scene_id": "scene-02",
  "start": 3.2,
  "end": 3.7,
  "timing_basis": "authored",
  "sound": {
    "asset_id": "openverse-selected-id",
    "revision": "selected-file-revision",
    "duration": 0.5,
    "volume": 0.25
  }
}
```

通过原事件导出器生成 `derived/sound-cues.json`，导出器从 `event.start` 生成 cue 的 `time`；不要手改派生 cue。导出命令见 [生产事件与工具](events-and-tools.md)，已有工程保留其原协议。

```sh
python3 "$SKILL/scripts/generate_sfx_tags.py" "$PROJECT/hf/index.html" \
  --manifest "$PROJECT/assets.lock.json" --cues "$PROJECT/derived/sound-cues.json"
# 核对只读结果后，使用相同参数加 --apply，才写入工程。
```

已有 FFmpeg／EDL 工程沿原混音链消费相同时间信息，不为了接入搜索更换渲染器。音效接线工具会验证本地文件、hash、音频长度和 cue 边界；这不能证明音效已经出现在最终 MP4。应用后把真实音频和变动的 HTML 加入构建依赖，重新导出构建证据、渲染，检查实际音轨。

## 5. 成片试听与交付

听最终文件的动作点、起止接缝、突兀峰值、人声遮挡和重复音效。人声段适当降低音量、必要时加淡入淡出；不套一个固定音量到所有来源。响度检测、全片解码与来源核验按现有交付流程执行。

交付保留实际选用音频、来源／署名、素材锁、声音时间源和输出证据。未试听标待试听，下载失败标失败；只有元数据或 JSON 导出不算入片。选中素材留在项目即可，不强制回填网盘或建设中央库。局部替换只重验受影响片段、接缝和最终混音。

## 接口依据与验证边界

接口字段与音频端点可核对 [官方音频视图](https://github.com/WordPress/openverse/blob/main/api/api/views/audio_views.py)、[音频序列化器](https://github.com/WordPress/openverse/blob/main/api/api/serializers/audio_serializers.py) 和[通用媒体序列化器](https://github.com/WordPress/openverse/blob/main/api/api/serializers/media_serializers.py)。

2026-10-17 的[真实点击音示例](../examples/openverse-click/README.md)已用 Chrome 搜索 API、核原始许可、下载媒体 `url` 返回的 MP3、导出时间线 cue 并接入 FFmpeg 测试片。最终文件完整解码通过，解码音轨在指定时间与源音相关系数约 0.998，证明真实声音已入片。示例使用公开 HQ MP3 预览，原站原件下载需登录，两者不能混称；主观试听仍待验。此证据只覆盖该样本与当时入口，不保证所有检索结果可下载，也不代替实际作品的试听。
