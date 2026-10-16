# 素材、品牌与私有配置

## 默认来源

1. 当前项目已有且许可明确的素材。
2. 新音效走 [Openverse](openverse-sfx.md)，运动设计走 [动效与音效](motion-and-sound.md)。
3. 真实通用 B-roll 缺件时走 [在线画面素材](stock-footage.md)；解释图与概念画面优先代码或生成。

旧的本机集中素材库、网盘冷库、目录索引、入库／回填、推荐与定时维护均退出视频生产；失败时也不回退到旧库。百度网盘作为通用资料读取工具独立保留，取论文、文稿等资料不触发素材库流程。项目内已采用的文件和配音模型缓存属于工程依赖，按原工程继续使用。

每个缺件先描述镜头作用、情绪、能量、时长、画幅和事实要求。每轮最多 3 个候选、最多两轮词；选中才下载，找不到就改画面方案。仅保留项目采用文件和短期网络缓存，不编目全站、不自动同步网盘、不新建中央库。

在项目 sources.json 或现有素材锁中记录来源页、作者、许可／授权依据、用途、本地相对路径和 SHA256。下载权限不等于公开商用权。品牌标识使用原文件。

## 品牌配置

显式设置 SANSHENG_VIDEO_PROFILE_DIR 时读取该目录 profile.json；否则只识别用户主动建立的仓根 profile/（可为链接）。运行 `python3 setup.py --show-profile` 获取真实配置与根目录。配置错误明确报错，不默默改品牌。

推荐字段见 profile.example/profile.json：brand、content_rules、output_root、legacy_root。legacy_root 仅用于已有生成执行器等私有能力，不是素材目录。旧配置中的 asset_roots、cold_storage_root 被忽略且不向 Agent 暴露。资源相对 profile 解析；交付只复制实际采用且有权使用的文件。profile 不保存密钥。
