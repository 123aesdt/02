export type Risk = "HIGH" | "MEDIUM" | "LOW";

export interface AnomalyRecord { id: string; taskId: string; orderId: string; type: string; risk: Risk; driver: string; vehicle: string; route: string; status: string; occurredAt: string; description: string; }
export interface OrderRecord { orderId: string; taskId: string; customer: string; driver: string; vehicle: string; route: string; status: string; eta: string; updatedAt: string; }
export interface MemoryRecord { memoryId: string; entities: string; scenario: string; resolution: string; similarity: string; vectorDimension: number; adoptedBy: string; updatedAt: string; }

export const anomalies: AnomalyRecord[] = [
  { id: "ANM-20260821-017", taskId: "TASK-20260821-0042", orderId: "CF-20260821-00128", type: "暴雨道路湿滑", risk: "HIGH", driver: "李师傅", vehicle: "苏G·A8126", route: "新平路", status: "已完成调度", occurredAt: "20:04", description: "李师傅在雨天经过新平路，道路出现湿滑风险。" },
  { id: "ANM-20260821-016", taskId: "TASK-20260821-0041", orderId: "CF-20260821-00127", type: "道路封闭", risk: "HIGH", driver: "王师傅", vehicle: "苏G·N2148", route: "东河乡道", status: "处理中", occurredAt: "19:42", description: "施工导致东河乡道完全封闭，等待路线决策。" },
  { id: "ANM-20260821-015", taskId: "TASK-20260821-0040", orderId: "CF-20260821-00126", type: "车辆故障", risk: "MEDIUM", driver: "张师傅", vehicle: "苏G·B1092", route: "城北物流线", status: "已完成调度", occurredAt: "19:18", description: "发动机告警后已切换备用车辆。" },
  { id: "ANM-20260821-014", taskId: "TASK-20260821-0039", orderId: "CF-20260821-00124", type: "站点积压", risk: "MEDIUM", driver: "刘师傅", vehicle: "苏G·K6630", route: "308县道", status: "人工复核", occurredAt: "18:56", description: "东南配送站出现货物严重积压。" },
  { id: "ANM-20260821-013", taskId: "TASK-20260821-0038", orderId: "CF-20260821-00123", type: "运力不足", risk: "LOW", driver: "陈师傅", vehicle: "苏G·E8199", route: "102国道", status: "已完成调度", occurredAt: "18:31", description: "临时增加一台可用备用车辆。" },
  { id: "ANM-20260821-012", taskId: "TASK-20260821-0037", orderId: "CF-20260821-00122", type: "道路封闭", risk: "HIGH", driver: "赵师傅", vehicle: "苏G·C5521", route: "西山路", status: "已降级", occurredAt: "18:08", description: "路况服务商超时，已使用静态路线规则。" },
  { id: "ANM-20260821-011", taskId: "TASK-20260821-0036", orderId: "CF-20260821-00121", type: "天气预警", risk: "MEDIUM", driver: "周师傅", vehicle: "苏G·L7280", route: "永安大道", status: "已完成调度", occurredAt: "17:45", description: "短时强降雨预警已写入环境风险。" },
  { id: "ANM-20260821-010", taskId: "TASK-20260821-0035", orderId: "CF-20260821-00120", type: "车辆故障", risk: "LOW", driver: "孙师傅", vehicle: "苏G·H0031", route: "南环路", status: "已完成调度", occurredAt: "17:14", description: "胎压异常已由司机现场处理。" },
  { id: "ANM-20260821-009", taskId: "TASK-20260821-0034", orderId: "CF-20260821-00119", type: "站点积压", risk: "MEDIUM", driver: "吴师傅", vehicle: "苏G·M4682", route: "金湖路", status: "处理中", occurredAt: "16:48", description: "金湖配送站等待分流决策。" },
  { id: "ANM-20260821-008", taskId: "TASK-20260821-0033", orderId: "CF-20260821-00118", type: "天气预警", risk: "LOW", driver: "钱师傅", vehicle: "苏G·P9110", route: "青阳路", status: "已完成调度", occurredAt: "16:09", description: "大风预警已写入安全提醒。" },
];

export const orders: OrderRecord[] = anomalies.map((anomaly, index) => ({ orderId: anomaly.orderId, taskId: anomaly.taskId, customer: ["新平商贸", "东河农产", "城北医药", "东南百货", "永安冷链"][index % 5], driver: anomaly.driver, vehicle: anomaly.vehicle, route: anomaly.route, status: anomaly.status, eta: index === 0 ? "21:12" : `${20 + (index % 3)}:${String(10 + index * 4).padStart(2, "0")}`, updatedAt: anomaly.occurredAt }));
export const memories: MemoryRecord[] = [
  { memoryId: "memory-rain-li", entities: "李师傅 · 新平路", scenario: "雨天道路湿滑风险较高", resolution: "建议改走102国道", similarity: "94.6%", vectorDimension: 2560, adoptedBy: "TASK-20260821-0042", updatedAt: "20:04" },
  { memoryId: "memory-engine-spare", entities: "张师傅 · 苏G·B1092", scenario: "车辆发动机故障", resolution: "更换备用车辆继续配送", similarity: "88.3%", vectorDimension: 2560, adoptedBy: "TASK-20260821-0040", updatedAt: "19:18" },
  { memoryId: "memory-station-divert", entities: "东南配送站", scenario: "站点货物严重积压", resolution: "分流至邻近配送站", similarity: "81.7%", vectorDimension: 2560, adoptedBy: "TASK-20260821-0039", updatedAt: "18:56" },
  { memoryId: "memory-road-closed", entities: "东河乡道", scenario: "道路完全封闭", resolution: "绕行备用县道", similarity: "78.1%", vectorDimension: 2560, adoptedBy: "TASK-20260821-0041", updatedAt: "19:42" },
];
