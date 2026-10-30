# 镜头请求模板：发给视频生成器的固定格式

用于逐镜生成的叙事片（Muse、Veo、Kling、Seedance 等入口都适用）：每条约 5～15 秒的镜头请求用同一套字段、同一个顺序，只往里填本镜内容。何时、怎样把请求交给 Muse 见 [Muse 交接](muse-handoff.md)；故事与关卡见 [电影感生成短片](cinematic-generated-film.md)。

核心原则：**镜头请求是控制文件，不是创作散文**。只写画面里看得见的结果，每张参考图只绑定一种用途，保持镜头内的因果，返修时只改对应失败的那几行。模型没有记忆，全片固定的描述每条请求都逐字重复，不缩写、不换同义词。

## 两层文本

1. **项目说明**：在一个生成对话开头发一次，或者每批请求开头发一次。顺序沿用公开 SOP 的 11 项，只保留生成器用得上的部分：
   1. 项目名称与目标；
   2. 输入素材及优先级（参考图的用途和顺序）；
   3. 技术规格（画幅、每条时长、声音方式）；
   4. 世界观、故事主线与本批所在段落；
   5. 角色、场景和道具的一致性约束；
   6. 逐镜请求（下一节的固定格式）；
   7. 环境声与拟音的要求；配乐不在这里，见 [原生声音与后期分工](generated-audiovisual.md#原生声音与后期分工)；
   8. 交付与清单要求（原片、实际发送的提示词、实际传入的图片、时长、分辨率，失败时写明原因）。

   剪辑、转场、调色和配乐由后期负责，不要求生成器去做。
2. **镜头请求**：每镜一条，字段和顺序固定如下。

## 镜头请求的字段与顺序

| 顺序 | 字段 | 写什么 | 为什么在这里 |
|---|---|---|---|
| 1 | `CAST` | `EXACTLY N CHARACTERS, NO DUPLICATES: 名字…. No other people.`；空镜写 `NO PEOPLE IN FRAME` | 人数锁放在最前，防止角色被复制、凭空多出路人 |
| 2 | `REFERENCES` | `image 1 = 用途; image 2 = 用途`，顺序与附件一致；身份参考写明「只取长相和服装，不继承背景、构图和画法」 | 每张图只承担一种用途，避免把参考图的背景或画幅带进画面 |
| 3 | `STYLE` | 全片风格句，逐字复用 | 风格句一换措辞，画风就会漂移 |
| 4 | `CHARACTER <名字>` | 每个出镜角色一句锚点：年龄感、发型与颜色、2 个以上不可混淆的服装或发饰、鞋、比例 | 全片只用这个名字指这个角色 |
| 5 | `WORLD` | 本段场景锚点：地形、季节、天气、主光方向。只写环境，不写某个揭示镜头才出现的物件 | 写进场景锚点的物件，每一镜都可能提前出现 |
| 6 | `FORMAT` | 画幅、单一连续镜头、画面无文字、无 Logo、无水印 | 固定的输出项 |
| 7 | `FIRST FRAME (0s)` | 景别、机位高度和方向、人物在画面里的位置（frame-left、frame-right、前景、中景、背景） | 首帧图已经交代的内容，这里只补图上看不出来的 |
| 8 | `ACTION` | `0-3s / 3-7s / 7-10s` 三拍，全镜只有一个主要动作；每个变化都要有看得见的原因 | 一镜一个动作；复杂动作放在前半段 |
| 9 | `CAMERA` | 一种运镜，加上速度和停止点；固定机位写 `Locked <景别>. The camera remains still. No push, no zoom.` | 不写停止点，后半段容易自己推近或跑偏 |
| 10 | `LIGHT`（可选） | 本镜的光向和色温，和首帧一致 | 与相邻镜头对得上 |
| 11 | `AMBIENT MOTION` | 两种以上环境微动，如风、云影、水光、飘落物 | 画面要「活」，靠的是环境在动 |
| 12 | `END STATE (10s)` | 人物位置、朝向、道具在谁手里，再重复一遍人数 | 供下一镜衔接，也是对人数的第二道锁 |
| 13 | `CUTS TO`（可选） | 下一镜从什么状态开始，靠什么衔接，比如动作、视线、形状或声音 | 让末态朝着下一镜的首帧去 |
| 14 | `AUDIO` | `Ambience`（本镜真实空间的环境声）、`Foley`（可见事件 → 声音）、`Music: none (…added in post)`、`Voice`（无对白片写 `no dialogue, no narration`）、`Mix` | 声音单独成块；配乐整片另做 |
| 15 | `CONTINUITY` | 保持参考图里的角色造型、服装和颜色 | 收尾再强调一次 |

```text
CAST: EXACTLY 1 CHARACTER, NO DUPLICATES: MINA. No other people.
REFERENCES: image 1 = first frame of this shot (composition, positions, style); image 2 = MINA identity only (face, hair, outfit), do not inherit its background or layout
STYLE: <全片风格句>
CHARACTER MINA: <角色锚点句>
WORLD: <本段场景锚点>
FORMAT: 16:9 landscape, single continuous shot, clean frame with no text, logo or watermark.
FIRST FRAME (0s): wide shot from child eye height; MINA small at frame-left by the stone well; the village lane leads to frame-right.
ACTION: 0-3s MINA leans over the well rim, the red spool in her right hand / 3-7s her foot slips on the wet stone and she tips forward / 7-10s she drops into the dark mouth of the well, the spool still in her hand
CAMERA: Locked wide shot. The camera remains still. No push, no zoom.
AMBIENT MOTION: wind moving her hem and the grass; a few leaves drifting across the lane
END STATE (10s): only MINA's legs and red ribbon still visible, vanishing into the dark well mouth at frame-left. Exactly 1 character in frame: MINA.
CUTS TO: the next shot starts inside the well, MINA falling through soft light.
AUDIO:
  Ambience: light wind in the lane, distant birds
  Foley: shoe scraping on wet stone at 4s; a soft rush of air as she falls
  Music: none (no background music; the score is added in post)
  Voice: no dialogue, no narration.
  Mix: ambience and foley natural and clearly audible.
CONTINUITY: preserve the referenced character design, outfit and colors exactly.
```

## 写法规则

- **用正向写法**：写想要的画面，不写禁止清单。「不要」只用在字幕、Logo、水印、对白这类明确的输出项，以及人数锁和机位锁。
- **一镜一个动作**：走近、失足、落下这类连续动作，各自拆成一镜；复杂动作从动作中途开始，「走过去」单独一镜。
- **情绪写成可见动作**：低头、停步、手指收紧、回头看，而不是「她很难过」。
- **一个角色一个名字**：全片固定一个大写名字，中途登场写 `the same <名字>`，不用 `a tall figure` 这类会被理解成另一个人的称呼。
- **属性只属于一个角色**：容易串的属性写成「红发带只属于 MINA」。
- **时间窗是导演意图**：模型不会逐秒执行，动作量要和时长相称，后半段留给动作完成和稳定。
- **全片用同一种语言写请求**：给编排者的说明可以用中文；中英文效果谁更好，未经对照不下结论。

## 发送前自查

逐镜过一遍下面的问题。任何一项答不上来，就改镜头，不要把它留给模型去猜。

- 这个东西为什么会动？力从哪里来？施力的人或物离它够不够近？
- 人物的姿势是否承接上一镜的末态？
- 被用到的道具，在用之前已经出现过了吗？
- `CAST` 的人数和 `END STATE` 里的人数一致吗？首帧图里有没有提前画进后面才登场的人？
- 世界或空间的跨越（掉进井里、穿过门）有没有拆成「临界动作 → 过程 → 抵达」几镜？
- `CAMERA` 写了停止点吗？固定机位是不是用的 `Locked … remains still`？

## 返修纪律

- 一次只诊断一个故障，最多改 5 行，其余有效的行原样保留。旧版本全部保留，新版不一定比旧版好，要对比。
- 同一故障反复出现时，按这个顺序加码：普通描述 → 精确描述（写明数量、位置、方向）→ 大写的归属或数量锁 → 拆成两镜。
- 一镜试了 10～15 次仍不收敛，就简化镜头：拆成两镜、去掉一个动作或换个角度，不再改措辞。
- 每次生成后，在生产日志里追加一行：`| 镜号 | 请求版本 | 改了什么 | 结果 | 判定 |`。
- 同样的提示词原样重抽是正常手段：公开档案显示成熟制作的大部分生成都是原样重抽，所以先判断是运气问题还是写法问题，再决定改不改。

## 用镜头表批量拼请求

整片镜头写成一张 JSON 镜头表，用 `python3 scripts/assemble_shot_requests.py <镜头表> --out <目录>` 按上面的字段顺序拼出每批请求。

**镜头表结构**
- `locks`
  - `style`：风格句，可以写多个变体。
  - `characters`、`names`：角色锚点句和角色的大写名字。
  - `worlds`：场景锚点。
  - `refs`：参考图的文件和用途。
  - `format`、`voice`、`mix`、`continuity`：其余固定项。
- `segments`：把段落映射到场景锚点。
- `shots`：每镜的字段。
  - 必填：`first_frame`、三段 `action`、`camera`、`ambient`、`end_state`、`ambience`、`foley`。
  - 选填：`characters`、`extras`（不在角色锁里的人，例如 `one old woman`，会计入人数）、`refs`、`light`、`next`、`world`、`batch`、`seconds`。

**脚本行为**
- 自动生成 `CAST` 人数锁，并在 `END STATE` 末尾重复一遍人数。
- 参考图按顺序绑定用途。
- 默认写 `Music: none`；只有 `locks.native_music` 为 true 时，才按段落音乐锁写入原生配乐，此时每镜必须填 `music_dynamic`。
- 校验缺字段、重复编号，以及引用了未定义的锁或参考图。

**常用参数**
- `--shots S13,S35`：只拼这几个镜头，用于试片。
- `--style <变体名>`：拼风格对照版。

试片后只改锁或镜头表，然后重新拼装，不要手改已经拼好的请求。

## 来源

- 控制文件原则、人数锁、归属锁、`Locked … No push, no zoom`、因果自查、只改一行和升级顺序、原样重抽的比例：[hindsight-video-prompting](https://github.com/gvago/hindsight-video-prompting)，从 AI 长片《Hell Grind》约 10 万次生成档案提炼，开源。
- 先锁定资产再生成、固定 15 块提示词、一镜一个动作、生产日志格式、15 次不收敛就简化：[film-studio-skills](https://github.com/machina-exm/film-studio-skills)，开源，可装进 Claude Code 或 Codex 的 skill 链。
- 各家共有字段（主体、动作、场景、镜头、光与风格、声音）：[Veo 3.1 官方指南](https://cloud.google.com/blog/products/ai-machine-learning/ultimate-prompting-guide-for-veo-3-1)、[Kling 官方指南](https://kling.ai/blog/kling-ai-prompt-guide)、[Runway Gen-4 官方指南](https://help.runwayml.com/hc/en-us/articles/39789879462419-Gen-4-Video-Prompting-Guide)；正向写法和固定机位的说法来自 Runway。
- 项目说明的 11 项：X 用户 vincent_ddup《ChatGPT × Muse 标准制作 SOP》，个人经验。资产先行、一镜一种运镜、情绪写成可见动作：X 用户 jarvis11x《如何利用 Muse 制作一部 3 分钟一集的漫剧》，个人经验，转述 Seedance 官方文档和 Higgsfield 的方法。
- 本页字段顺序是对以上来源的归纳，各家顺序并不统一（Veo 把镜头放第一，Seedance 把主体放第一）；JSON 格式的提示词只见于社区模板，没有官方对照实验，所以这里用带标签的纯文本。
