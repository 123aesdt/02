# Task 8 实施报告：车辆接替与动态路线可视化

## 基线与范围

- 固定 BASE：`5a09a6cbdb30bc89dc88ce75ac38d1e578c65a75`。
- 开始前工作树：干净。
- 本任务只修改前端类型、adapter 消费、可视化组件、详情页组合、虚拟演示数据和前端测试；未修改后端契约，未接入高德或任何外部地图。
- 所有新增可见文案为中文；算法名、车辆/司机/道路 ID 保留原始代码，便于老师核对计算证据。

## TDD 红灯证据

1. 首轮车辆、动态地图与 adapter：
   - 命令：`npm.cmd test -- tests/fleet-allocation-panel.test.tsx tests/dynamic-route-visual.test.tsx tests/api-dispatch-adapter.test.ts`
   - 结果：exit 1；车辆面板模块尚不存在；动态地图 2 项失败（仍为固定 `viewBox="0 0 650 270"`、空证据仍展示硬编码路线）；adapter 既有 13 项通过。
2. 持久路线计算面板：
   - 命令：`npm.cmd test -- tests/dispatch-v2-evidence.test.tsx`
   - 结果：exit 1；`route-plan-result-panel` 模块尚不存在。
3. Result 详情页恢复：
   - 命令：`npm.cmd test -- tests/task-events-lifecycle.test.tsx`
   - 结果：`1 failed, 7 passed`；Result 已包含证据，但页面尚未显示“替代车辆调度计算”。
4. 旧演示页兼容：
   - 命令：`npm.cmd test -- tests/localized-business-copy.test.tsx`
   - 结果：`2 failed`；仪表盘和模拟详情的道路元素数量均为 0，证明动态化后旧调用方缺少数据源。
5. 道路去重：
   - 命令：`npm.cmd test -- tests/dynamic-route-visual.test.tsx`
   - 结果：`1 failed, 1 passed`；重复 E07 被画成两个元素，并触发 React 重复 key 警告。

6. 独立审查两项 Important 修复：
   - 命令：`npm.cmd test -- tests/fleet-allocation-panel.test.tsx`
   - 结果：exit 1，`2 failed, 1 passed`；旧实现为陌生车辆构造重复身份标题且没有语义表，行为测试按预期阻断。

## 实现结果

### TypeScript 响应契约

- 逐字段镜像后端 `FleetScoreComponentsResponse`、`RouteScoreComponentsResponse`、`PathResponse`、`VehicleCandidateResponse`、`VehicleAllocationResponse`、`RoadNodeResponse`、`RoadEdgeResponse`、`RouteCandidateResponse`、`RoutePlanResponse`。
- `TaskResultResponse` 增加 nullable `vehicle_allocation` 与 `route_plan`。
- 距离、坐标、评分、风险代价和其他 Decimal 字段均保持 `string`；adapter 不重命名 ID，也不把 Decimal 字符串转换为 number。

### 车辆接替面板

- 新增 `FleetAllocationPanel`，组件只接收 `VehicleAllocationResponse`。
- 同屏展示故障车辆、接替箭头、新车辆、司机、接驳距离/时间、入选评分、评分公式与六项评分分解。
- 候选区使用真正的语义 `<table>`，包含 `caption`、`thead`、`tbody`、列头及 `scope="row"` 行头；每行保留 `data-vehicle-id` 与只由 `vehicle_id` 组成的可访问标题。
- 每辆候选车逐项展示资格与全部排除原因、司机 ID/状态、车辆状态、剩余载重、总重、能力、接驳距离/时间、总分及六项评分分解；nullable 证据统一显示中性中文“未提供”。
- 身份信息只展示 `VehicleAllocationResponse` 中已有的 `vehicle_id`/`driver_id`，不再内置车牌或名称映射；选中只依据 `target_vehicle_id`，合格未选候选只显示“满足硬约束”，不推断评分高低。

### 动态 SVG 道路网络

- `RouteVisual` 现只消费调用方传入的 `RoutePlanResponse` 与可选接驳边 ID；组件内不再硬编码节点、道路名、固定 `d=` 或路线。
- 根据 API Decimal 坐标计算最小/最大边界和固定 1 公里 padding，生成 SVG viewBox。
- 根据 `edge_id` 去重，每条有效道路只画一次；缺失端点的边不绘制。
- 样式优先级固定为：堵塞 > 接驳 > 推荐 > 原路线 > 普通。
- 每条道路都有稳定 `data-edge-id`、`data-route-state` 和 `<title>`；节点也由 API 坐标与名称生成。
- 空路网、无原路线或无推荐路线均显示稳定中文空态，不抛异常。
- 旧仪表盘与模拟详情页显式传入本地 `mockRoutePlan`，因此未退化成空地图，同时保持动态组件本身无硬编码。

### 持久结果详情页

- Result 存在 `vehicle_allocation` 时显示车辆接替计算；存在 `route_plan` 时显示动态地图与完整重算过程。
- 路线计算区显示 Dijkstra/算法版本、道路网络版本、堵塞边、访问节点数、原/新节点和边序列、候选目标、原/新里程与耗时、里程和时间变化。
- 固定演示结果可直观看到 `V-001 → V-005`、司机 `D-003`、`接驳 2.80 公里 · 6 分钟`、评分 `93.4`，以及 E04 堵塞、E07 推荐、`+3.20 公里`、`+4 分钟`。
- 八 Agent 事件面板保持原数量和顺序；持久 Result 的测试在没有实时事件的刷新场景下仍恢复完整车辆与路线证据。

## 浏览器验收

- 继承的详情页视觉基线：`docs/assets/frontend-demo/dispatch-detail-1440.png`。
- 初版真实页面截图：`docs/verification/task-8/offline-dispatch-result.png`；它记录审查修复前的页面，本轮只修复两项 Important，未将旧截图误称为最终表格证据。
- 内置浏览器运行工具未向当前子任务暴露，因此按规范回退到仓库已有 Playwright Chromium；Vite 以 API 模式启动，HTTP 接口由本地完整虚拟 Result 拦截，不访问外部网络。
- 第一次 Playwright 运行因“王主管”定位器同时匹配 3 个元素而失败；根因明确后仅将定位器收窄为 `exact: true`。复跑结果：`1 passed (1.8s)`。
- 验收视口：1440 × 1200，full-page 截图。
- 核对点：
  1. “替代车辆调度计算”和“新路线规划计算”标题均可见；
  2. 接驳距离/时间与 `+3.20 公里` 可见；
  3. E04 DOM 状态为 blocked，E07 为 recommended；
  4. 八 Agent `.pipeline-item` 数量严格为 8；
  5. 页面完整截图成功生成，未出现 Playwright 可见性失败。
- 首屏文案差异：未改变既有任务标题、状态、导航和任务上下文；新增证据面板位于既有状态说明之后。
- 受 Windows sandbox deny-read ACL 影响，Codex `view_image` 无法直接重新打开基线图和最新截图；没有伪称完成图像像素级对比。Playwright 已完成真实 Chromium 的可见性、结构、状态和截图验证。

## 最终验证记录

- 初版聚焦核心测试：`5 passed` 文件，`27 passed` 测试；独立审查修复聚焦测试：`1 passed` 文件，`3 passed` 测试。
- 旧演示页兼容测试：`2 passed` 文件，`4 passed` 测试。
- 完整前端测试：`54 passed` 文件，`250 passed` 测试，exit 0。
- `npm.cmd run lint`：exit 0，0 errors；保留两个既有 Fast Refresh warnings，位置为 `router.tsx` 与 `dev-role-preview.tsx`。
- `npm.cmd run build`：exit 0；TypeScript 与 Vite 构建成功，转换 1919 个模块。
- Vite 保留一个非阻塞提示：主 bundle 压缩后超过 500 kB；本任务未引入第三方依赖，也未扩展范围做全局代码分割。
- `git diff --check`：exit 0；仅有 Git 的 LF/CRLF 工作副本提示，无空白错误。
- 新增行五类敏感格式扫描：OpenAI 样式密钥 0、AWS 访问密钥 0、私钥头 0、URL 内嵌凭据 0、JWT 0。

## 已知限制

- 后端当前响应不包含车牌或车辆名称字段，因此界面按 API 权威数据只显示车辆 ID；简报示例中的“新物冷链-01/05”无法由当前 Result 证明，若未来确需展示，应先由后端契约提供公开字段。
- API 生产路径会展示后端持久化的完整 18 节点、26 边；旧 mock 页面使用较小的本地示例路网，仅用于不启动后端时保持演示可见。
- 整体旧详情页在 1180px 以下沿用项目既有最小宽度布局；候选证据表在窄容器中提供横向滚动，未扩大范围重构整个旧 App Shell。
