import { anomalies, memories, orders, type AnomalyRecord, type MemoryRecord, type OrderRecord, type Risk } from "../mocks/workspace-data";
import { runtimeConfig } from "../config/runtime";

type Filters = { query?: string; risk?: Risk | ""; type?: string; status?: string };
function ready() { if (runtimeConfig.dataMode !== "mock") throw new Error("Workspace data requires its FastAPI adapter in API mode; Mock fallback is forbidden."); }
function matches(values: string[], query?: string) { const terms = query?.trim().toLowerCase().split(/\s+/).filter(Boolean) ?? []; return terms.every((term) => values.some((value) => value.toLowerCase().includes(term))); }
export async function getAnomalies(filters: Filters = {}): Promise<AnomalyRecord[]> { ready(); return anomalies.filter((item) => matches([item.id, item.orderId, item.driver, item.type], filters.query) && (!filters.risk || item.risk === filters.risk) && (!filters.type || item.type === filters.type) && (!filters.status || item.status === filters.status)); }
export async function getOrders(filters: Pick<Filters, "query" | "status"> = {}): Promise<OrderRecord[]> { ready(); return orders.filter((item) => matches([item.orderId, item.driver, item.customer, item.vehicle], filters.query) && (!filters.status || item.status === filters.status)); }
export async function getMemoryRecords(filters: Pick<Filters, "query"> = {}): Promise<MemoryRecord[]> { ready(); return memories.filter((item) => matches([item.memoryId, item.entities, item.scenario, item.resolution], filters.query)); }
