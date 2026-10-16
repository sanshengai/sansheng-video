# 在线真实画面：只解决当前镜头缺件

借鉴 [MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo) 的素材入口，不采用它的随机素材拼片流程。官方 `app/services/material.py` 当前包含 Pexels、Pixabay、Coverr；它的关键词与分辨率筛选不能证明画面事实匹配。

## 来源与取舍

- **Pexels 主源**：自然、城市、办公等通用情境可用；先看主体、构图、运动和画幅是否适合当前镜头。[许可](https://www.pexels.com/license/)允许免费使用和修改，有人物、品牌等限制；不是无版权。
- **Pixabay 备用**：Pexels 两轮无合适候选或明确需要补充题材时才用；[许可摘要](https://pixabay.com/service/license-summary/)与具体作品页面同时留证。照片／视频与音乐不可混为同一权利判断。
- **Coverr 暂不默认接入**：[许可](https://coverr.co/license)支持多种免费使用，但搜索中也可能有第三方付费内容；与前两源覆盖重叠，不值得每镜再多搜一轮。仅有明确特定候选时人工核对。

商业图库适合概括场景，不适合作为某位人物、企业或历史事件的实拍证据。一页课桌的教学关系用代码图解和既定角色解释，不为了好看插入无关商业图库。第三方人物／商标／场景的使用权依具体镜头判断，网站免费标签不能代替判断。

## 有界调用

只有镜头需要通用真实 B-roll 且当前工程无合适画面时触发。先写镜头目的和英文关键词，每轮最多 3 个候选、最多 2 轮；找到可用的即停止。默认只查 Pexels，必要时再去 Pixabay，不做全源并搜、全站爬取、定时囤积或中央目录。

```sh
python3 scripts/stock_media.py search 'quiet city morning' --orientation landscape --out PROJECT/stock-search.json
python3 scripts/stock_media.py fetch --record PROJECT/stock-search.json --id SELECTED_ID --output PROJECT/assets/city.mp4
```

Pexels API 需要已有授权的 `PEXELS_API_KEY`。没有 key 或 API 不可用时，命令返回同源网页地址与 `browser_required`；用浏览器看最多三个候选，将所选条目的 provider、id、page_url、creator、license_url、url 记录为 JSON，再执行 fetch。**未配置 key 不等于 API 搜索已验证**。不自动注册、付费、寻找隐藏凭证或偷偷切源。Pixabay 当前走网页选定记录，未实现 API 搜索。

API 搜索缓存 6 小时、每次最多 3 条，先选不超过 1080p 的 MP4。只有选定条目下载；下载后 ffprobe 校验真实视频并旁写 `.source.json`（作者、落地页、许可链接、SHA256、实际尺寸时长）。源记录不自动标许可／画面审查通过。保留具体页面和使用时的许可证据，选中的媒体进入当前项目素材锁和镜头时间线；默认不混入图库原声。

来源多不会自动提高片子质量。预算是每个缺件镜头 3 个候选、2 轮；不建第二个素材管理系统，不回填旧本机／百度网盘库。工程中自己的媒体继续正常用，网盘只在明确取资料任务中独立调用。

实测：未配 API key 时，通过同源网页选定 [Mak_ jp 的街景视频](https://www.pexels.com/video/sunlit-urban-street-with-trees-at-sunrise-33472428/)，再由 fetch 下载、校验通过（1080×1920）。抽帧显示阳光穿树的街景，可作氛围画面；页面标签不能证明具体城市。API 在线搜索仍未实测。
