# 真实网页介绍

先写一条用户任务：入口 → 操作 → 可见反馈 → 结果去向。采集时实际完成该任务，核对按钮、状态与复制内容。浏览器内保存、服务端配置和交给 AI 生效是三种结果；不能把网页中的选择演成已经修改本机 Skill。模拟助手窗口只可标为示意，不能虚构 AI 已经回复或生成。

可用真实录屏，或真实状态截图加合成光标、镜头和字幕。按可读性选，交付准确说明方法。只采本片需要的状态，不为验收反复下载整个安装包。平台或网站变化时定向重采，不牵连无关镜头。

## 采集适配

使用宿主已有、获授权的专用浏览器。不要为本工具另装 Playwright、启动用户主浏览器或切换引擎。已有 Playwright `page` 可调用可选适配：

```javascript
import {captureWebState} from './path/to/scripts/capture_web_state.mjs';
await captureWebState(page, {
  output: '/project/capture/before.json', id: 'before',
  controls: {save: '#save-default', feedback: '#feedback'}
});
// 实际操作和等待真实反馈，再采 after。滚动/缩放/状态改变后重新采。
```

返回 viewport 截图、URL、时间、DPR、滚动、DOM 控件文字／位置和状态指纹。采集期间控件几何或内容改变则拒绝。控件只记录当前视口可见对象；滚动后重新取，不能沿用之前的坐标。已观察到本次复制内容时可传 `copied: {method: 'intercepted_writeText', text: 实际本次写入文本}`，或 `observed_copy_result`。拦截写入须在项目采集前明确设置并记下方法；不读无关的系统剪贴板，也不凭示例文本填入。

宿主没有 Playwright 时沿原浏览器工具采集相同信息；不把旧截图补造为新实测。历史工程缺少上下文绑定时记录缺项，来源还有效即可定向复用，不宣称已通过新适配的全部验收。

## 任务与构建

任务文件例子（文件路径相对任务文件）：

```json
{
  "kind": "web-walkthrough/1", "task": "保存偏好并交给助手",
  "states": ["before.json", "after.json"],
  "steps": [{
    "id": "save", "before": "before", "after": "after",
    "control": "save", "control_text": "保存为默认",
    "scope": "browser_local", "feedback_control": "feedback",
    "result": "已保存在此浏览器", "next_step": "复制偏好交给助手后才修改 Skill"
  }]
}
```

`scope` 可为 `view`、`navigation`、`browser_local`、`server`、`clipboard` 或 `agent_handoff`。复制和交接需要 after 的真实 `copied` 记录；其他结果引用 after 的实际反馈控件。浏览器本地保存补明后续步骤及边界。记录了 `server` 本身不是服务端变更证明，仍须实测响应或读回依据；结果文字正确性由制作 Agent 核实。

```bash
python3 scripts/web_walkthrough.py project/capture/task.json
```

需要进入宣传片构建时，将任务文件作为 [brief 证据](promotion-evidence.md) 并加 `"kind": "web-walkthrough"`。导出会读取截图和控件，锁定任务、所有状态及截图的指纹，并写进 `promotion-plan.json`。镜头使用其已解析截图和控件坐标，画面仍须实际预览。改变视口／截图／坐标上下文、缺控件、按钮文案不符、缺反馈时拒绝对应任务。验证的是采集一致性与来源，没有自动判断网站语义、真人操作或审美的能力。
