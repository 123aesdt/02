# 县域物流异常识别与智能调度系统——需求分析与WBS拆解文档

> 任务一正式交付物。Word 版本为主提交文件，本 Markdown 版本用于项目仓库留档与后续维护。

## 1 业务背景
县域及乡村物流常见恶劣天气、道路封闭、车辆故障、站点积压、运力不足等异常。传统调度高度依赖个人经验，历史经验无法沉淀，高并发改派存在覆盖冲突，长耗时路径/AI调用可能阻塞 API，天气/路况第三方服务也可能超时。

核心长期经验示例：**李师傅 + 雨天 + 新平路 + 湿滑风险 → 历史建议改走102国道**。项目将其沉淀为 Driver/Route/Anomaly/Resolution 的 Entity-Relation Memory。

## 2 目标用户
- 调度员：处理异常、查看候选路线与AI决策。
- 物流主管：监督履约、风险、人工复核与审计。
- 系统运维/管理员：监控 Redis、Worker、数据库、Qdrant 与性能。

## 3 核心问题
1. 异常响应依赖人工经验。
2. 历史经验无法复用。
3. 多人并发修改存在调度冲突。
4. 长耗时 Agent/路径计算阻塞 API。
5. 外部环境 API 不稳定。
6. Worker 崩溃会造成任务停滞。
7. 重试可能导致重复派单。
8. 决策缺乏解释和审计。

## 4 用户角色
详见 Word 正式版角色矩阵。

## 5 核心业务流程
异常上报 → FastAPI → Redis Streams → Worker → Intake → Entity Memory → Environment → Capacity → Routing → Dispatch → Audit → DB 持久化 → XACK → Redis Task Event Stream → WebSocket → 前端。

## 6 MVP必须功能
七Agent、Entity Memory/Qdrant、Redis Streams/Worker、乐观锁、幂等防重、环境超时/Fallback/Circuit Breaker、Audit、前端控制台、Docker Compose、Locust。

## 7 可选功能
真实GIS、更多模型Provider、DLQ重放、企业微信/短信告警、历史分析、完整可观测平台。

## 8 暂不实现功能
微服务、Kubernetes、Kafka/RabbitMQ、完整GIS、多租户复杂权限、全局分布式Circuit Breaker、大模型训练平台。

## 9 异常场景
覆盖环境API超时、Qdrant失败、Redis不可用、Worker崩溃、Pending、Retry/DLQ、重复消息、幂等冲突、乐观锁冲突、Capacity不可用、无安全路线、Audit失败、WebSocket断开等。

## 10 待确认问题与最终决策
详见 Word 正式版决策表。

## 11 1人1周WBS
原工单阶段人日合计为 8.0，但总工时又写 7 人日。提交版保留该冲突，并给出压缩后的 **7.0 人日执行WBS**。

## 12 需求修改意见汇总
包括：模块化单体、Provider抽象、异步Worker、0.8秒降级、process-local Breaker、MVP Capacity/Route Provider、Effectively-Once、Mock→Real Adapter、Redis Event Stream等。

> 完整内容、表格、异常矩阵、验收指标映射和当前实现状态以 Word 正式版为准。
