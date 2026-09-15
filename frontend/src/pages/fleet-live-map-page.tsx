import { ExternalLink, Radio, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { FleetSandboxMap } from "../components/fleet-sandbox-map";
import { EmptyState } from "../components/ui/empty-state";
import { Skeleton } from "../components/ui/skeleton";
import { DataSourceBadge } from "../components/ui/data-source-badge";
import { StatusBadge } from "../components/ui/status-badge";
import { RoleWorkspaceFrame } from "../components/workspace/role-workspace-frame";
import { WorkspaceSection } from "../components/workspace/workspace-section";
import { runtimeConfig } from "../config/runtime";
import { anomalyDisplayLabel, problemTypeLabel, taskDisplayId, taskStatusLabel } from "../features/fleet-sandbox/fleet-sandbox-data";
import { useTaskApi } from "../hooks/use-task-api";
import { useTaskEvents } from "../hooks/use-task-events";
import { useVehicleOperationSnapshot } from "../hooks/use-vehicle-operation-snapshot";
import { useAnomaliesRead } from "../hooks/use-workspace-reads";
import type { AnomalyListItem } from "../types/workspace-read-models";

function FleetLiveTaskMap({ taskId, anomaly }: { taskId: string; anomaly: AnomalyListItem }) {
  const [refreshKey, setRefreshKey] = useState(0);
  const refresh = useCallback(() => setRefreshKey((current) => current + 1), []);
  const task = useTaskApi(taskId, refreshKey);
  const realtime = useTaskEvents(taskId, refresh);
  const breakdown = (task.result?.anomaly_type ?? anomaly.anomaly_type).toUpperCase() === "VEHICLE_BREAKDOWN";
  const operation = useVehicleOperationSnapshot(taskId, null, breakdown);

  if (task.loading) return <section className="fleet-command-loading" role="status" aria-label="车辆态势地图加载中">
    <div className="fleet-command-loading__copy">
      <span><Radio size={15}/>实时地图初始化</span>
      <h2>正在建立车辆运行态势</h2>
      <p>车辆与路线数据加载中；完成前不展示历史车辆或旧任务路线。</p>
    </div>
    <Skeleton label="正在同步车辆、站点与道路规划" lines={6} />
  </section>;
  if (task.error) return <EmptyState kind="error" title="地图任务加载失败" description={task.error.message} action={<button type="button" onClick={refresh}>重新读取</button>} />;
  if (!task.status) return <EmptyState kind="empty" title="没有可显示的任务状态" />;

  return <>
    <div className="fleet-map-task-summary">
      <span><small>AI 调度任务</small><strong>{taskDisplayId(anomaly.row_id)}</strong></span>
      <span><small>问题类型</small><strong>{problemTypeLabel(task.result?.anomaly_type ?? anomaly.anomaly_type)}</strong></span>
      <span><small>异常状态</small><strong>{taskStatusLabel(task.status.status)}</strong></span>
      <span><small>实时通道</small><strong>{realtime.connection === "CONNECTED" ? "已连接" : realtime.connection === "RECONNECTING" ? "重连中" : "未连接"}</strong></span>
      <Link to={`/dispatch/${taskId}`}>查看完整调度证据 <ExternalLink size={14}/></Link>
    </div>
    <FleetSandboxMap
      anomalyType={task.result?.anomaly_type ?? anomaly.anomaly_type}
      allocation={task.result?.vehicle_allocation}
      routePlan={task.result?.route_plan}
      connection={realtime.connection}
      reportedVehicleId={anomaly.vehicle_id}
      taskStatus={task.status.status}
      events={realtime.events}
      operationSnapshot={operation.snapshot}
    />
  </>;
}

export function FleetLiveMapPage() {
  const anomalies = useAnomaliesRead({ limit: 50 });
  const [selectedTaskId, setSelectedTaskId] = useState("");
  const candidates = anomalies.state === "READY"
    ? anomalies.data.items.filter((item): item is AnomalyListItem & { latest_task_id: string } => Boolean(item.latest_task_id))
    : [];

  useEffect(() => {
    const timer = window.setInterval(anomalies.refresh, 3000);
    return () => window.clearInterval(timer);
  }, [anomalies.refresh]);

  if (runtimeConfig.dataMode !== "api") {
    return <RoleWorkspaceFrame title="车辆态势地图" description="查看员工上报后的车辆异常、AI 派车与虚拟路线运行状态。"><EmptyState kind="not-exposed" title="实时地图仅在 API 模式开放" /></RoleWorkspaceFrame>;
  }

  if (anomalies.state === "LOADING") {
    return <RoleWorkspaceFrame title="车辆态势地图" description="查看员工上报后的车辆异常、AI 派车与虚拟路线运行状态。"><Skeleton label="正在读取最近异常任务" lines={7} /></RoleWorkspaceFrame>;
  }
  if (anomalies.state !== "READY") {
    const title = anomalies.state === "EMPTY" ? "暂无可显示的异常任务" : anomalies.state === "FORBIDDEN" ? "没有读取异常任务的权限" : "异常任务读取失败";
    return <RoleWorkspaceFrame title="车辆态势地图" description="查看员工上报后的车辆异常、AI 派车与虚拟路线运行状态。"><EmptyState kind={anomalies.state === "FORBIDDEN" ? "forbidden" : anomalies.state === "EMPTY" ? "empty" : "error"} title={title} action={anomalies.state === "EMPTY" ? undefined : <button type="button" onClick={anomalies.refresh}>重试</button>} /></RoleWorkspaceFrame>;
  }

  if (!candidates.length) {
    return <RoleWorkspaceFrame title="车辆态势地图" description="查看员工上报后的车辆异常、AI 派车与虚拟路线运行状态。"><EmptyState kind="empty" title="最近异常尚未生成调度任务" description="员工上报并生成任务后会自动出现在这里。" /></RoleWorkspaceFrame>;
  }
  const activeTaskId = candidates.some((item) => item.latest_task_id === selectedTaskId)
    ? selectedTaskId
    : candidates[0].latest_task_id;
  const activeAnomaly = candidates.find((item) => item.latest_task_id === activeTaskId) ?? candidates[0];

  return <RoleWorkspaceFrame
    title="车辆态势地图"
    description="员工上报后自动联动车辆状态、AI 替代车辆和重新规划路线。"
    actions={<div className="workspace-action-cluster"><DataSourceBadge provenance={anomalies.data.provenance} detail="后端异常任务与车辆处置快照"/><StatusBadge status="LIVE" label="每3秒自动同步上报" /></div>}
  >
    <WorkspaceSection id="fleet-live-sandbox" title="县域车辆实时沙盘" description="选择最近异常任务；车辆沿高德规划道路连续移动，运行状态定时校准。">
      <div className="fleet-map-headbar"><div className="fleet-map-toolbar">
        <label><span><Radio size={14}/>异常调度任务</span><select aria-label="选择地图任务" value={activeTaskId} onChange={(event) => setSelectedTaskId(event.target.value)}>{candidates.map((item) => <option key={item.latest_task_id} value={item.latest_task_id}>{anomalyDisplayLabel(item)}</option>)}</select></label>
        <button type="button" className="secondary-action" onClick={anomalies.refresh}><RefreshCw size={14}/>刷新</button>
      </div></div>
      <FleetLiveTaskMap key={activeTaskId} taskId={activeTaskId} anomaly={activeAnomaly}/>
    </WorkspaceSection>
  </RoleWorkspaceFrame>;
}
