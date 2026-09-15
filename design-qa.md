# Agent 流水线设计验收

- source visual truth path: `C:/Users/24090/AppData/Local/Temp/codex-clipboard-2aee0a0f-f275-4049-8aeb-ec3948a9b913.png`
- implementation collapsed screenshot: `docs/verification/agent-pipeline/agent-pipeline-collapsed.png`
- implementation expanded screenshot: `docs/verification/agent-pipeline/agent-pipeline-expanded.png`
- normalized comparison: `docs/verification/agent-pipeline/source-vs-implementation.png`
- source pixels: 381 × 627
- implementation pixels: collapsed 286 × 561；expanded 286 × 870
- viewport: 1470 × 1000 CSS px
- device scale factor: 1
- density normalization: 对照板把两侧等比归一到 381 px 宽；源图保持 381 × 627，实现折叠态归一为 381 × 747
- state: 八个 Agent 已完成；折叠态与“路径智能体”展开态

## Browser-rendered evidence

- Deterministic mock implementation URL: `http://127.0.0.1:5174/dispatch/TASK-20260821-0042`
- Docker demo URL: `http://127.0.0.1:5173/dispatch/TASK-20260821-0042`
- Playwright result: 1 passed.
- Primary interactions tested: 定位八个 Agent、确认无原始 JSON、展开路径智能体、确认一次仅一个明细、校验读取信息/执行动作/输出结果/关键证据/事件 ID。
- Browser console and page errors checked: 0 errors.
- Vite error overlay checked: absent.

## Full-view comparison evidence

源图和实现折叠态已放入同一张 `source-vs-implementation.png` 对照板。实现保留了源图的纵向节点轨道、状态色、紧凑窄栏和 Agent 顺序。主要产品改进是把原图中被截断的 JSON 改成可读中文工作结果，并增加明确的展开箭头；实际 286 px 栏宽下摘要自然换行，没有水平溢出或内容裁切。

## Focused region comparison evidence

`agent-pipeline-expanded.png` 单独捕获了路径智能体展开态。读取信息、执行动作、输出结果形成连续三步；关键证据采用两列卡片；事件类型、事件 ID 和耗时位于低权重底栏。全部信息保持在 286 px 面板内，没有遮挡下一 Agent。

## Findings

没有可执行的 P0、P1 或 P2 差异。

## Required fidelity surfaces

- Fonts and typography: 延续现有中文无衬线体系；Agent 名称、摘要、技术事件信息形成三级字重。摘要允许换行，技术字段仅在展开态显示。
- Spacing and layout rhythm: 节点、连接线、摘要和展开卡片对齐稳定；展开后纵向节奏仍连续。实现比源图更高是可读摘要替代单行截断 JSON 的预期结果。
- Colors and visual tokens: 保留深蓝背景、青绿色成功、琥珀色降级、红色失败语义；展开卡片使用现有品牌边框与表面 token。
- Image quality and asset fidelity: 该组件没有业务图片资产；交互图标使用项目既有 Lucide 矢量图标，1× 截图清晰。
- Copy and content: 八个 Agent 均展示中文工作结果；展开态包含输入、动作、结果、关键证据、事件 ID 和耗时。

## Comparison history

1. Initial QA pass: blocked，因为当前会话没有交互式浏览器控制接口，尚无浏览器截图或控制台证据。
2. Fix/evidence: 增加项目 Playwright 端到端用例，启动确定性 mock 页面，捕获折叠态与路径 Agent 展开态，检查控制台、页面错误和 Vite overlay。
3. Post-fix comparison: 将源图与实现折叠态按相同宽度放入同一对照板；检查展开态聚焦截图。无 P0/P1/P2 差异。

## Implementation checklist

- [x] 保留八节点纵向流水线和状态语义。
- [x] 折叠态展示每个 Agent 的可读中文结果。
- [x] 展开态展示输入、动作、结果、关键证据、事件 ID 和耗时。
- [x] 一次只展开一个 Agent，失败项优先展开。
- [x] API 事件使用后端白名单字段，mock 模式具备完整演示数据。
- [x] 完成浏览器截图、交互、控制台和同屏设计比较。

final result: passed
