# 高德小货车 HUD 设计验收

- source visual truth path: `.superpowers/brainstorm/countyflow-repair-map-20260910/content/vehicle-marker-hud.png`
- selected vehicle asset source: `C:/Users/24090/.codex/generated_images/01a0a2f1-abe8-7131-91a9-e9a073aa56ff/exec-26e3f0d9-fae4-436a-9d01-829ecd6a1510.png`
- project vehicle asset: `frontend/public/assets/fleet/vehicle-top-view.png`
- implementation screenshot path: `.superpowers/brainstorm/countyflow-repair-map-20260910/content/vehicle-hud-cargo-map.png`
- full-page screenshot path: `.superpowers/brainstorm/countyflow-repair-map-20260910/content/vehicle-hud-cargo-page.png`
- full-view comparison: `.superpowers/brainstorm/countyflow-repair-map-20260910/content/vehicle-hud-cargo-comparison.png`
- focused comparison: `.superpowers/brainstorm/countyflow-repair-map-20260910/content/vehicle-hud-cargo-focused-comparison.png`
- source pixels: 1487 × 1058
- implementation pixels: 876 × 589
- viewport: 1440 × 1000 CSS px
- implementation component size: 876 × 589 CSS px
- device scale factor: 1
- density normalization: 将目标稿纵向居中裁为 1487 × 1000，再缩放至 876 × 589；实现截图保持原生 876 × 589，左右并排为 1752 × 589。
- state: Docker 高德地图 READY；10 条道路完成真实道路匹配；20 辆车可见；V-009 行驶中车辆通过真实指针点击选中并打开右侧详情卡。

## Browser-rendered evidence

- implementation URL: `http://localhost:5173/fleet-live-map`
- browser path: Browser 技能已列出，但工具发现未提供可调用的 Browser JavaScript 入口；按前端测试规范回退到仓库现有 Playwright。
- Playwright flow: 管理员登录 → 进入车辆态势地图 → 等待高德地图 READY 与 10 条道路完成 → 确认 20 张小货车 PNG 的 naturalWidth/naturalHeight 均有效 → 定位未遮挡的行驶中车辆 → 真实指针点击 → 确认选中态和信息卡可见。
- selected detail: `V-009 / 38 km/h / 行驶中 / 路线-05 · 南部村镇支线 / 南环中段`。
- selected marker box: 74.24 × 74.24 CSS px（64 px HUD 经选中缩放）。
- selected info box: 194 × 127.86 CSS px，位于车辆右侧。
- framework error overlay: absent。
- browser console: 0 application errors。
- existing fleet loading E2E: 1 passed。
- visual interaction E2E: 1 passed。

## Full-view comparison evidence

目标稿与最终真实高德地图截图已放入同一张 1752 × 589 对照图。实现保留当前产品的真实高德道路、站点、救援单元、图层控件和数据密度，只重做车辆视觉。两侧在车辆选中状态下均具备俯视车辆、状态光晕、雷达双环、方向提示和深色信息卡。概念稿的浅色简化地图与实现的真实业务地图属于有意产品约束，不计为车辆 UI 偏差。

## Focused region comparison evidence

聚焦对照同时展示目标稿的 V-005 选中区域和实现的 V-009 选中区域。实现的小货车驾驶室、后部货厢、四轮和青色描边在 35 × 48 px 显示尺寸下可识别；选中双环和航向随道路切线旋转。信息卡改为车辆右侧锚定，车辆主体不再被卡片覆盖，并补充真实路线名称与位置。

## Findings

没有剩余可执行的 P0、P1 或 P2 差异。

## Required fidelity surfaces

- Fonts and typography: 沿用产品中文无衬线字体；车号 15 px、速度 13 px、状态 12 px、路线与位置 10–11 px，层级与目标稿一致，动态长路线使用截断保护。
- Spacing and layout rhythm: HUD 从旧 44 px 扩为 64 px，选中态约 74 px；双环间距为 7 px；信息卡 194 px 宽并以 `middle-left + [46, 0]` 放在车辆右侧。
- Colors and visual tokens: 行驶中青色、调度中紫色、待命灰色、故障红色；各状态共享深色车身并通过状态色描边、环形光效和图例表达。
- Image quality and asset fidelity: 使用用户确认的真实生成小货车 PNG，不再使用通用 `CarFront` 线框图标。最终项目资产为 192 × 256、32bpp ARGB、74 KB；已裁除透明留白并按地图槽位优化，未观察到背景色或透明边缘残留。
- Icons: 航向使用现有 Lucide `Navigation` 图标库，不使用手绘 SVG；车辆主体使用生成位图。
- Copy and content: 图例完整显示行驶中、调度中、待命、故障；详情卡显示车辆 ID、速度、状态、路线和位置。
- Accessibility: 车辆 Marker 保持原生 button 与中文 aria-label；图片为装饰性空 alt；状态不只依赖颜色，还通过图例、详情文字和故障/调度标签表达。
- Responsiveness: 本轮目标是 1440 × 1000 现场大屏；现有 760 px 响应式规则保留。未将移动端视觉作为本轮阻断项。

## Comparison history

1. P1 — 初始实现使用通用 `CarFront` 线框图标，只呈现深色圆形按钮，不像目标稿车辆。修复：生成并接入用户确认的俯视小型厢式货车 PNG。
2. P2 — 初次接入的 1053 × 1493 原图透明留白过大，缩到地图后车身偏小。修复：检测非透明边界 473 × 968，裁边并输出 192 × 256 透明项目资产。
3. P2 — HUD 扩大后仍沿用 12–16 px 的旧避让半径，中心车辆重叠。修复：按集群规模将避让半径调整为 32 / 40 / 48 px，并增加最小中心距离测试。
4. P1 — 高德 Marker 点击冒泡与 `closeWhenClickMap: true` 竞争，InfoWindow 创建后立即变为 `display:none`。修复：让详情卡随 React 选中状态持续显示，切换车辆时仍关闭旧卡片。
5. P2 — 信息卡在车辆上方居中，真实地图中覆盖车辆和邻近标记。修复：改为 `middle-left` 右侧锚点和 46 px 间距。
6. Post-fix evidence — 最终截图显示行驶中小货车、双环、航向、避让和右侧信息卡；Playwright 确认信息卡父级 `.amap-info` 为 `display:block`，无应用控制台错误或框架错误浮层。

## Implementation checklist

- [x] 使用用户确认的小型厢式货车透明 PNG。
- [x] 地图标记与四态图例复用同一车辆资产。
- [x] 映射行驶中、调度中、待命、故障四种状态。
- [x] 使用可检查的内外双层雷达环。
- [x] 航向图标和车身随高德道路切线旋转。
- [x] 同点车辆按 64 px HUD 尺寸进行避让。
- [x] 选中信息卡保持可见并位于车辆右侧。
- [x] 保留车辆动画、真实道路、救援单元和点击选择逻辑。
- [x] 完成单元测试、Docker 构建、真实指针交互和同屏视觉比较。

## Follow-up polish

- P3: 真实高德地图在县域调度中心附近包含路线、站点、救援标签和多辆车，信息密度高于概念稿；若现场演示需要完全复刻概念稿的留白，可新增独立演示视角/图层预设，但不应删除真实业务信息或伪造车辆状态。

final result: passed
