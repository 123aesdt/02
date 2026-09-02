# 人工复核决定验证记录

验证日期：2026-08-30

## 验证范围

- 系统管理员和调度主管拥有人工复核权限；普通调度员无权提交决定。
- 批准与拒绝均通过后端接口写入本地演示 MySQL，不使用企业数据。
- 拒绝必须填写原因；重复提交和并发版本冲突有明确反馈。
- 页面提供确认弹窗，成功后重新读取真实待复核列表。
- 领域审计与安全审计均记录决定和操作身份。

## 自动化验证

- 后端 Ruff：通过。
- 后端 Pytest：`799 passed, 7 skipped`；跳过项均为需要显式开启的真实外部依赖测试。
- 前端 ESLint：通过，保留 2 条既有 warning，无 error。
- 前端 Vitest：`45 files, 207 tests passed`。
- 前端生产构建：通过，`1913 modules transformed`。
- 人工复核最终专项回归：`21 passed`。
- `git diff --check`：退出码 0；仅报告工作区既有的 LF/CRLF 转换提示，无空白错误。

## 真实 Docker 与 API 验证

- `scripts/start-full.ps1` 完整执行成功，后端、前端、Worker-1、Worker-2、Redis、MySQL、Qdrant、Neo4j、Prometheus、Grafana 全部就绪。
- 免密管理员账号：`CF-DEMO-005`。
- API 双向验证：批准 `DEMO-TASK-006`，拒绝 `DEMO-TASK-004`。
- 两条任务与调度状态分别持久化为 `APPROVED`、`REJECTED`，调度版本均从 1 增至 2。
- 拒绝原因、批准备注、复核人编号和复核人姓名均以 UTF-8 正确保存。
- 调度员提交返回 403；重复提交返回 409。
- 待复核总数从 4 降为 2。
- `security_audit_events` 记录 `REVIEW_APPROVED` 和 `REVIEW_REJECTED`。
- 最终状态为 10 个常驻服务运行、迁移服务退出码 0，共 11 个 Compose 服务。

## 真实浏览器验证

- Playwright：`1 passed`。
- 管理员在真实页面点击“批准”，确认弹窗可见并可填写说明。
- 点击“确认批准”后出现成功反馈，列表由 2 行刷新为 1 行，无浏览器控制台错误。
- 截图：`01-review-actions.png`、`02-approve-confirmation.png`、`03-review-refreshed.png`。

本次真实验证处理了三条本地演示记录，仍保留一条待复核记录供继续展示。
