# 高德车辆 HUD 设计验收

- source visual truth path: `.superpowers/brainstorm/countyflow-repair-map-20260910/content/vehicle-marker-hud.png`
- implementation screenshot path: `C:/Users/24090/.codex/visualizations/2026/09/15/01a0a2f1-abe8-7131-91a9-e9a073aa56ff/countyflow-vehicle-hud-map.png`
- full-view comparison: `.superpowers/brainstorm/countyflow-repair-map-20260910/content/vehicle-hud-comparison.jpg`
- focused comparison: `.superpowers/brainstorm/countyflow-repair-map-20260910/content/vehicle-hud-focused-comparison.jpg`
- source pixels: 1487 × 1058
- implementation pixels: 876 × 589
- viewport: 1440 × 1000 CSS px
- implementation component size: 876 × 588 CSS px
- device scale factor: 1
- density normalization: 全景对照板将两侧等比缩放至 720 px 宽并置于 720 × 540 画布；聚焦对照板将车辆与信息浮层裁切后统一为 600 × 416。
- state: Docker 高德地图 READY；10 条道路匹配完成；20 辆车可见；V-004 行驶中车辆已选中并打开详情。

## Browser-rendered evidence

- implementation URL: `http://localhost:5173/fleet-live-map`
- browser path: Browser 插件已列出，但当前会话没有可调用的 Browser JavaScript 入口；按前端测试规范回退到仓库现有 Playwright。
- Playwright E2E: `fleet-map-loading.spec.ts` 1 passed。
- primary interaction tested: 管理员登录 → 进入车辆态势地图 → 等待高德地图与 10 条道路完成 → 选择一个未被浮层遮挡的行驶中车辆 V-004 → 确认选中态和车辆详情。
- rendered result: 20 个 HUD 标记；8 个行驶中、12 个待命；当前实时演示数据没有调度中或故障车辆，右下角四态图例仍完整展示行驶中、调度中、待命、故障。
- selected detail: `V-004 / 38 km/h / 行驶中 / 路线-02 · 南环快速配送线 / 南环中段`。
- framework error overlay: absent。
- browser console: 0 application errors；仅有无头 Chromium WebGL `ReadPixels` 与 Canvas2D `willReadFrequently` 性能警告，来自地图渲染层，不影响功能。

## Full-view comparison evidence

选中视觉稿和真实高德地图截图已放入同一张对照板。实现保留现有调度大屏、真实道路与高德地图密度，只替换车辆视觉语言：深色玻璃核心、状态色雷达双环、随道路方向旋转的箭头、选中发光态和右下角四态图例。视觉稿使用生成的浅色概念地图，而实现继续使用产品当前真实地图主题，这是避免重做地图产品层的有意差异。

## Focused region comparison evidence

聚焦对照板同时展示视觉稿与实现的选中车辆区域。两者都具备清晰的选中环、车辆方向提示、状态色与深色信息浮层；实现浮层补齐真实车牌、速度、状态、路线名称和位置。真实地图车辆更密集，因此实现的 44 px 标记和 194 px 浮层比概念稿更紧凑，未遮挡地图主要操作区。

## Findings

没有可执行的 P0、P1 或 P2 差异。

## Required fidelity surfaces

- Fonts and typography: 沿用项目中文无衬线字体；车号 15 px、速度 13 px、状态 12 px、路线与位置 10–11 px，层级清晰且没有截断关键信息。
- Spacing and layout rhythm: 标记保持 44 × 44 px，方向图形位于中心，异常标签向右展开；图例固定右下角，信息浮层与现有 AMap 布局兼容。
- Colors and visual tokens: 行驶中青色、调度中紫色、待命灰色、故障红色；深海军蓝表面、低强度外发光和双环选中态与视觉稿一致。
- Image quality and asset fidelity: 车辆与方向图形使用项目现有 Lucide `CarFront`、`Navigation` 矢量图标；不再使用 CSS 绘制卡车，不存在位图拉伸、透明边缘或占位资产。
- Copy and content: 四态中文图例完整；选中浮层显示车辆 ID、速度、状态、路线和当前位置。

## Comparison history

1. Initial implementation comparison: 标记四态、选中浮层和方向旋转均存在，但实时演示数据没有调度中/故障实例，现场无法直接看到全部颜色。
2. Fix: 按选中视觉稿补充右下角四态车辆图例，不伪造实际车辆状态；增加行为测试并重新构建 Docker 前端。
3. Post-fix evidence: 最终 Docker E2E 通过；真实车辆点击、选中态、详情浮层、四态图例、道路匹配与控制台健康均验证通过；全景和聚焦对照无 P0/P1/P2 差异。

## Implementation checklist

- [x] 使用真实图标库替换 CSS 卡车拼图。
- [x] 映射行驶中、调度中、待命、故障四种 HUD 状态。
- [x] 方向箭头随现有高德道路航向旋转。
- [x] 选中车辆使用双环高亮并展示车号、速度、状态、路线和位置。
- [x] 保留车辆动画、重叠避让、点击选择和高德路线逻辑。
- [x] 增加四态图例，保证无异常演示数据时仍可完整展示视觉系统。
- [x] 完成 Docker E2E、交互截图、控制台检查和同屏设计比较。

## Follow-up polish

- P3: 若后续需要更贴近概念图，可在专门的“演示数据模式”中注入一辆调度中和一辆故障车辆；生产/真实数据模式不应伪造状态。

final result: passed
