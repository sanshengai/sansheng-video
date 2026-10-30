# 风格包：日式手绘奇幻电影

当作者要的整体气质是「日式手绘奇幻长片」（常被称作宫崎骏式、吉卜力式）时读本页。本页把这种气质拆成画面、人物、运镜、剪辑和声音上可描述、可检查的特征，供写风格句、配乐要求和镜头请求时取用。叙事与制作顺序见 [电影感生成短片](cinematic-generated-film.md)，请求格式见 [镜头请求模板](shot-request-template.md)。

默认用下面的属性来描述，不在请求里点名在世导演、作曲家、工作室或作品。原因有三个：一是模型对名字的理解不稳定，常混成泛日漫画风；二是点名会把知名作品的标志意象一起带进来；三是 2025 年起部分生成平台对点名这类风格的请求做过限制，可能直接被拒。若作者希望对照，在代表镜试片里同一镜头各做一版（属性描述版、点名版），按实际效果记录，不预设哪种更好；被拒就记录原文，不换词绕过。

**实测状态（2026-10）**：用 Muse 按本页的属性描述，加上 Muse 自己生成的角色和场景参考图，做了一部 4 分钟、42 镜的短片。作者看完的判断是「整体不像」：人物塑造、画法和颜色都不对，但说不出具体是哪个词。中途从「偏暗、过浓」调成「明亮、中低饱和」，也没有解决。原因还没查清，几种可能是：
- 属性词只能描述表层特征；
- 参考图由同一个模型生成，偏差一路累积；
- 静图认可以后，没有在动态小样上再确认一次。

所以本页的写法只能当作起点，不能当作做出这种风格的保证。下一次先按 [电影感生成短片 · 画风关卡](cinematic-generated-film.md#3-制作顺序每道关卡过了才花下一笔额度) 做动态小样，作者认可后再批量生成；把每次换方向的结果补进本页，包括参考图来源、风格句和作者的判断。

## 画面

| 特征 | 怎么写、怎么查 |
|---|---|
| 背景是主角之一 | 手绘水彩/水粉质感，笔触可见，细节密度高；背景比人物更精细 |
| 天空与云 | 大面积天空，体积感强的积云，有受光面和阴影面；云影在地面上移动 |
| 风 | 风几乎一直在：草浪成片起伏，头发、衣摆、树叶跟着同一个风向动 |
| 光 | 自然光有明确方向：夏日强光配清晰阴影，午后侧光，黄昏金色逆光，窗内暖光对室外冷光 |
| 色彩与明度 | 高明度、中低饱和、通透明亮：天空是清澈的浅蓝到钴蓝，云是白的、阴影是浅灰蓝，草木是明快的黄绿，整体像晴天里的空气。避免浓烈饱和、整体发紫发蓝、霓虹色和橙色滤镜；黄昏和雪夜也保持明亮通透，不压暗 |
| 人物造型 | 线条干净，五官简洁圆润，眼睛不过分大、不带多层高光；孩子是真实的孩子比例 |
| 动作有重量 | 跑时身体前倾、停步时衣服因惯性继续摆一下；抱重物时腰往后仰；惊奇时身体先停住，眼睛慢慢睁大 |
| 生活细节 | 食物冒热气、手被烫到缩回、用袖子擦脸；奇幻世界里也保留这些日常动作 |
| 留白时刻 | 有不推动情节的安静镜头：人物坐着看风景、风吹过空无一人的草地；这类镜头让奇幻显得可信 |
| 「間」：镜头内的停顿 | 和留白镜头不同，是情节镜头里一个不推进情节的小动作：叹一口气、看一眼溪水、拉一下衣角。每个约 10 秒的镜头可放一个，写进 ACTION 的中段或末段。检查：删掉它剧情不变，但人物变得只是在「忙」，就该保留 |
| 色彩从背景出发 | 先定背景色板（天、草、屋顶、墙的主色），人物服装从这套颜色里取或与之协调，不另加霓虹或高饱和点缀；强调色只留给项目指定的一两样东西 |
| 阴影浅而有色 | 阴影是浅的、透明的，带一点环境色（天光的浅蓝、草地的绿、木头的暖褐），不用纯黑或中性灰，也不能深到压暗画面。不要在提示词里写「蓝紫阴影」：实测会把整片画面推向深紫。检查：截帧里没有死黑色块，暗部仍能看清细节 |
| 食物与器物 | 好看靠热气、油光、边缘高光和手的动作（掰开、吹凉、烫到缩手），不写「精致摆盘」；玻璃、水面写反光与透出的背景 |
| 奇幻物理自洽 | 会飞、会漂浮、会动的东西要写清靠什么动（翅膀、气流、绳子拉）和动之前的预备动作；重力可以被打破，但打破的方式全片一致 |

风格句示例（按项目调整，全片逐字复用）：

```text
hand-painted 2D animation in the tradition of classic Japanese fantasy feature films:
soft, light and airy watercolor-and-gouache backgrounds with visible brushwork, bright
high-key natural daylight and clear clean air, luminous sunlit cumulus clouds with soft
pale shadows, gentle natural colors with high brightness and moderate saturation, light
transparent shadows, clean simple character linework with natural proportions, wind
constantly moving grass, hair and cloth, tender, calm and beautiful
```

避免：3D 渲染或塑料质感、写实照片质感、大眼闪光的当代日漫画风、电子游戏式特效光。

**画风会随场景内容漂移**：食物特写容易变写实照片，夜景和发光物容易变 3D 渲染，人物近景容易变当代日漫画风。对策是全片锁里的风格句逐字不换（不换同义词、不调语序），并在风格句末尾加一句短的排除，例如 `not 3D, not photorealistic, not glossy modern anime, not dark, not oversaturated`。这是输出画风这类明确项，适用「否定只用于明确输出项」的例外。效果在代表镜试片里对照有无这句来确认。

## 运镜与剪辑

- **机位高度**：多数镜头在人眼或孩子眼睛的高度；俯瞰与仰视留给揭示和飞行。
- **运动方式**：大景多为固定机位或很慢的横移、上摇、升降；很少用推拉变焦和手持晃动。人物与环境在画面里动，相机克制。
- **停留**：风景镜头停得久，让观众看完风和云的变化；动作段落才短切。
- **揭示**：常用「先看人物的反应，再给她看到的景象」：先拍人物停步、抬头、睁大眼睛，再切到全景或慢慢上摇揭示。
- **转场**：直切为主；时间与空间的大跳跃用淡出淡入或白光，不用花式转场。

## 声音与配乐

| 层 | 特征 | 写给配乐的描述示例（配乐整片单独做，不写进镜头请求） |
|---|---|---|
| 主旋律 | 简单好记、能哼出来，像民谣或童谣，在家里钢琴上就能弹；常以钢琴独奏首次出现，和声不堆叠 | `a simple, memorable piano melody, tender and nostalgic` |
| 编制 | 管弦乐为底：弦乐、长笛、单簧管、圆号、竖琴、钢片琴；高潮时全编制合奏同一旋律 | `full warm orchestra carrying the main melody on strings and horns, broad and soaring` |
| 节奏 | 华尔兹、慢板或轻快的进行；不用流行鼓点 | `a gentle waltz in three, moderate tempo` |
| 进入时机 | 音乐常在画面打开、人物看见新世界时进入；安静段落让环境声主导 | `the music enters softly as the view opens up` |
| 环境与拟音 | 真实细腻、偏安静：风、草、木头、水、布料；不夸张、不卡通化 | `soft wind through tall grass, distant birds, wooden creaks` |

避免：电子合成器音色、预告片式重击打击乐、满铺的合唱、每个动作都配夸张音效。

## 自查

- 截一帧当壁纸：背景是否有足够的手绘细节，天空和云是否在画面中有分量。
- 关掉声音看一段：风是否让画面一直在动，人物动作是否有重量。
- 只听不看：主旋律是否在开场、高潮、结尾三处出现，安静段落是否留给了环境声。
- 对照风格句逐项看特写镜头：线条、五官与配色是否和全景是同一种画风。
- 截帧查明度：整体是否明亮通透；有没有纯黑、中性灰或深紫的大块阴影。
- 雪景、夜景、云中这类场景最容易变暗、变紫、变成 3D 质感。场景锁里不要写 `dusk`、`cold grey-blue air` 这类词，写「初雪的白天、明亮柔和的天光」；发光的东西写「纯白色、只有很淡的白色微光」，不要写 `golden light`、`glowing`，否则容易染成金色或粉色；雪花写「像真实落雪那么小、柔软」，否则会画成巨大的六角冰晶。参考图和首帧图在投入生成前，先缩成灰度图算平均亮度，和全片其他镜头比对；明显偏低的图会把整段带暗，先换掉。
- 逐镜问一次：这一镜里有没有一个不推进情节的小动作；全片是不是一直在「忙」。

## 来源

- 「間」与背景定色：宫崎骏 2002 年接受 Roger Ebert 访谈，转引自 [No Film School](http://nofilmschool.com/2013/09/master-of-ma-director-hayao-miyazaki-set-to-retire)。
- 高明度低饱和、有色阴影、食物与玻璃：色彩设计保田道世的工作方式，见 [Animation Obsessive · The Artist Who Colored Ghibli](https://animationobsessive.substack.com/p/the-artist-who-colored-ghibli)。
- 奇幻物理：[Physics in animation and in the films of Hayao Miyazaki](https://journal.animationstudies.org/article/id/91/)（Animation Studies）。
- 旋律取向：久石让自述，见 [Hollywood Bowl 节目说明](https://www.hollywoodbowl.com/musicdb/pieces/7848/program-note-joe-hisaishi-film-music-concert)。
- 风格头锁定与排除句：[ai-video-pipeline](https://github.com/0xadvait/ai-video-pipeline) 的做法（每格提示词以同一段风格头开头，否则画风随场景漂移）；方向相反（它排除手绘以保 3D），机制相同。
- 平台对点名风格的限制：[Business Insider，2025-03](https://www.businessinsider.com/openai-chatgpt-studio-ghibli-style-images-generation-grok-claude-genai-2025-3)。

以上是方法归纳，不复制原作画面，也不代表任何工作室认可。
