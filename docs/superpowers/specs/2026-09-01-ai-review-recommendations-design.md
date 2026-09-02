# CountyFlow AI 人工复核建议闭环设计

> 设计日期：2026-09-01（Asia/Shanghai）
> 状态：待用户确认后实施
> 适用范围：司机异常上报 → 8-Agent 分析 → 人工复核 → 结果发布 → 司机查看

## 1. 问题与根因

真实司机上报任务已经完成 8 个 Agent 节点，并在 Runtime Thread 中形成 `decision_reason`、运力判断、记忆命中和人工复核结论。但当前 `DispatchService` 在 `MANUAL_REVIEW` 分支提前返回，不创建 `Dispatch`；人工复核列表只读取 MySQL 中的 `Dispatch` 和 `AuditRecord`，因此原因与建议路线显示为空。`ReviewDecisionService` 又要求存在持久化 `Dispatch`，导致这些空白任务无法形成完整审批闭环。

旧的 `DEMO-TASK-001` 能显示原因和路线，是因为 seed 预先写入了静态 `Dispatch`，不能代表实时 Agent 输出已经正确投影。

## 2. 目标

1. 识别道路、天气、车辆、轮胎、货物、运力及其他问题，不把所有问题解释为道路问题。
2. 将“建议路线”和“AI 处置建议”分离；非道路问题不虚构路线。
3. 每个进入人工复核的任务都持久化可审计的 `REVIEW_REQUIRED` 调度草案。
4. 复核列表明确显示 AI 分析原因、AI 处置建议、建议路线和分析状态。
5. 没有路线但有安全处置建议的方案可以批准并把处置指令发布给司机。
6. 幂等修复当前已经处于 `REVIEW_REQUIRED`、但缺少草案的历史任务。

## 3. 非目标与诚实边界

- 不新增第 9 个 Agent，继续使用现有 8-Agent 图。
- 不接入未配置的生产 LLM，也不把确定性规则伪装为大模型生成。
- 不为不存在的道路、车辆或救援资源生成虚假标识。
- 不把“换胎”“车辆救援”等动作写入 `target_route_id`。
- 不改变 MySQL 是业务事实源、Redis 是运行态与队列的边界。

前端统一使用“8-Agent 协同分析”或“AI 协同分析”措辞；只有实际 LLM Provider 启用后才能展示“大模型生成”。

## 4. 问题识别与建议策略

新增纯领域服务 `IssueRecommendationService`。它不访问 MySQL、Redis、Qdrant、Neo4j 或供应商 SDK，只消费已经进入 GraphState 的结构化事实：

- `anomaly_type`
- `anomaly_description`
- `vehicle_status`
- `environment_risk`
- `capacity_state`
- `candidate_routes`
- `recommended_route`
- 记忆命中摘要

结构化 `anomaly_type` 是主分类，司机描述用于识别子类型和补充建议。首版规则如下：

| 主类型 | 可识别子类型 | 无可用路线时的处置建议 |
|---|---|---|
| `VEHICLE_BREAKDOWN` | 轮胎/爆胎/扎胎、制动、发动机、一般故障 | 安全停车、设置警示、道路救援；轮胎问题优先换胎，严重故障建议换车转运 |
| `ROAD_BLOCKED` | 封路、塌方、积水、施工 | 停在安全位置，保持任务暂停，等待调度核实并配置替代路线 |
| `ROAD_HAZARD` | 湿滑、坑洼、落石、道路损坏 | 降速或停止通行，上报现场位置；有安全候选路线才建议改道 |
| `WEATHER` | 暴雨、大雪、大雾、强风 | 暂缓通行、就近避险，等待环境风险下降或调度确认替代路线 |
| `CARGO` | 破损、泄漏、温控、倾斜 | 停车检查、隔离风险、重新固定或转运货物 |
| `CAPACITY` | 司机不可用、车辆不可用、超载 | 重新分配司机或车辆，必要时拆单转运 |
| `OTHER` | 未归类现场问题 | 保持任务暂停并联系调度员，人工补充资源与方案 |

输出 `IssueRecommendation`：

- `issue_category`: 规范主类型。
- `issue_subtype`: 识别到的具体子类型或 `GENERAL`。
- `analysis_reason`: 中文、可审计的分析原因，必须引用真实输入事实。
- `recommended_action`: 中文处置建议，不能为空。
- `recommended_route`: 只有现有 Routing Provider 返回安全候选路线时才有值。
- `analysis_mode`: 固定为 `EIGHT_AGENT_RULE_ASSISTED`。

## 5. Graph 与服务边界

保持 8 个节点顺序不变。在现有 Routing 节点内，先执行 `RoutingService`，再用 `IssueRecommendationService` 结合问题上下文补充结果。GraphState 新增：

- `identified_issue`
- `issue_subtype`
- `recommended_action`
- `analysis_mode`

`decision_reason` 改为面向业务人员的中文 AI 分析原因。原 Routing Provider 的技术原因保留在证据中，不直接作为唯一用户文案。

Dispatch 节点把 `decision_reason`、`recommended_action`、`analysis_mode` 和可选路线一起交给 `DispatchService`。

## 6. 持久化与并发

### 6.1 Dispatch 草案

`dispatches` 新增：

- `recommended_action TEXT NULL`
- `analysis_mode VARCHAR(32) NULL`
- `issue_subtype VARCHAR(32) NULL`

新代码写入的人工复核草案要求 `recommended_action` 和 `analysis_mode` 非空；列保持数据库可空以兼容历史记录。

`DispatchService.execute` 不再在人工复核分支提前返回，而是幂等创建或读取一条 `status=REVIEW_REQUIRED` 的 `Dispatch`：

- `target_route_id` 可以为空。
- `decision_reason` 必须保存。
- `recommended_action` 必须保存。
- `executed=false`，表示尚未执行路线或处置方案。
- 返回真实 `dispatch_id`、`dispatch_no` 和 `version`。

继续使用 `version_id_col`；并发修改转换为现有 409 冲突，不用 Python 值比较模拟锁。

### 6.2 Audit

Audit 节点取得真实 `dispatch_id` 后持久化 `REVIEW_REQUIRED` 审计记录。`evidence_json` 继续保存有界图记忆证据，并增加：

- `analysis_mode`
- `identified_issue`
- `issue_subtype`
- `environment_risk`
- `capacity_status`
- `memory_hit_count`

不得记录鉴权头、密钥或未经限制的完整外部响应。

## 7. 人工复核读模型与 UI

复核 API 保留现有字段以兼容客户端，并新增：

- `ai_analysis_reason`
- `ai_recommended_action`
- `ai_analysis_mode`
- `issue_subtype`

字段来源必须是持久化 `Dispatch`；列表读取不直接依赖 Redis 检查点。

复核页面调整为：

- “原因”改为“AI 分析原因”。
- 新增“AI 处置建议”。
- “建议路线”没有值时显示“当前不适用”，不显示横线。
- 新增“8-Agent 分析完成”状态徽标。
- 任务编号继续链接到调度详情，详情展示节点进度、记忆、环境、运力和路由证据。

道路问题如果存在安全路线，同时显示建议路线与处置建议；轮胎等非道路问题显示“当前不适用”和具体处置建议。

## 8. 复核与发布

`ReviewDecisionService` 继续要求持久化草案。批准代表批准 AI 处置方案，不等同于路线一定存在。

`dispatch_publications` 调整为：

- `route_id` 改为可空。
- `route_instruction` 改为可空。
- 新增 `action_instruction TEXT NULL`。

发布规则：

- 有 `target_route_id`：发布路线说明，并同时发布处置建议。
- 无 `target_route_id`、但有 `recommended_action`：发布 action-only 指令，路线保持为空。
- 路线和处置建议都为空：拒绝发布并返回明确错误。

司机 My Tasks 新增“AI 处置指令”；未发布前继续隐藏主管尚未批准的最终方案。

## 9. 现有空白任务修复

新增显式、幂等的 `ReviewProposalRecoveryService` 和本地 CLI。它只处理：

- `DispatchTask.status == REVIEW_REQUIRED`
- 当前没有 `Dispatch`
- 存在可读取的终态 Runtime Thread 检查点

服务从检查点读取已经完成的 Agent 状态，使用相同推荐服务补全分析，创建草案与审计记录。重复运行不创建重复 Dispatch/Audit；检查点缺失的任务保持不变并报告任务编号，不生成猜测数据。

部署顺序：migration → backend/worker 重建 → 执行 recovery CLI → 前端重建。截图中的现有空白任务必须在验收中变为有 AI 分析原因和处置建议。

## 10. 错误处理

- 未识别子类型：回退主类型通用建议，不回退空字符串。
- 无安全路线：`recommended_route=null`，同时生成安全暂停/救援建议。
- Runtime checkpoint 缺失：恢复命令报告 skipped，不伪造结论。
- 草案持久化失败：Worker 不 ACK，沿用现有有界重试与 pending recovery。
- 推荐服务输入缺失：进入人工复核并生成保守建议，记录 `SOURCE_CONTEXT_INCOMPLETE` 证据。
- 发布内容为空：返回 409 `PUBLICATION_INSTRUCTION_MISSING`。

## 11. 测试策略

严格 TDD，至少覆盖：

1. 轮胎关键词得到轮胎子类型、救援/换胎建议且无虚假路线。
2. 道路阻断有安全候选路线时输出真实候选路线。
3. 道路阻断无候选路线时输出安全等待建议且路线为空。
4. 天气、货物、运力和 OTHER 都得到非空、类型匹配的建议。
5. 人工复核分支持久化唯一 Dispatch 草案和 AuditRecord。
6. 同任务重复执行不重复创建草案。
7. 复核列表返回 AI 原因、建议、模式和子类型。
8. 无路线草案可批准并发布 action-only 指令。
9. 司机只能在发布后看到处置指令。
10. recovery 修复有检查点的旧任务，跳过无检查点任务，重复运行幂等。
11. 前端表格显示“AI 分析原因”“AI 处置建议”“当前不适用”和分析状态。
12. 真实 Docker E2E：员工分别上报道路问题和轮胎问题，主管看到不同 AI 建议并完成复核。

## 12. 验收标准

1. 新的 `REVIEW_REQUIRED` 任务不再出现空原因和空建议。
2. 轮胎问题不会生成道路绕行建议。
3. 路线只来自 Routing Provider 的真实安全候选结果。
4. 所有问题类型都有非空处置建议。
5. UI 明确标注 8-Agent 分析，不声称未启用的 LLM。
6. 人工批准、发布和司机查看形成闭环。
7. 截图中已有空白任务完成幂等修复。
8. 后端 targeted/full tests、Ruff、前端 unit/lint/build 与真实 Docker E2E 通过。

