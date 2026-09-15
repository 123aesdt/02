import { Clock3, LifeBuoy, RefreshCw, ShieldCheck, Truck, Wrench } from "lucide-react";
import { useEffect, useState } from "react";

import { useDriverOperationSnapshot } from "../hooks/use-driver-operation-snapshot";
import { VehicleOperationTimeline } from "./vehicle-operation-timeline";

const rescueLabels: Record<string, string> = {
  CREATED: "救援任务已创建",
  DISPATCHED: "救援车辆已出发",
  ARRIVED: "救援车辆已抵达",
  LOADED: "故障车辆装载完成",
  DELIVERED: "故障车辆已送达维修站",
  FAILED: "道路救援失败",
  CANCELLED: "道路救援已取消",
};

const maintenanceLabels: Record<string, string> = {
  SCHEDULED: "维修工位已预约，等待车辆到站",
  WAITING_BAY: "车辆已到站，等待进入维修工位",
  DIAGNOSING: "维修人员正在检查故障",
  REPAIRING: "维修人员正在维修车辆",
  QA_PENDING: "维修已完成，正在进行安全质检",
  COMPLETED: "维修与安全质检已完成",
  FAILED: "维修或安全质检未通过",
  CANCELLED: "维修工单已取消",
};

function countdownLabel(seconds: number) {
  const safe = Math.max(0, seconds);
  const minutes = Math.floor(safe / 60);
  const remainder = safe % 60;
  return minutes > 0 ? minutes + " 分 " + remainder + " 秒" : remainder + " 秒";
}

const pendingEtaLabels: Record<string, string> = {
  SCHEDULED: "等待车辆到站",
  WAITING_BAY: "等待进入工位",
  DIAGNOSING: "诊断后生成",
  QA_PENDING: "等待安全质检",
  FAILED: "暂停恢复",
  CANCELLED: "工单已取消",
};

export function DriverOperationStatus({ taskId }: { taskId: string }) {
  const operation = useDriverOperationSnapshot(taskId);

  if (operation.loading) {
    return <div className="driver-operation-loading" role="status">正在同步救援与维修进度...</div>;
  }
  if (!operation.snapshot) return null;

  const snapshot = operation.snapshot;
  const recovered = snapshot.incident.status === "RECOVERED";
  const maintenanceSummary = snapshot.maintenance.status === "REPAIRING"
    ? snapshot.maintenance.diagnosis ?? "维修人员正在维修车辆"
    : maintenanceLabels[snapshot.maintenance.status] ?? "维修状态同步中";
  return <article className="driver-operation-status" data-driver-operation-status>
    <header>
      <div>
        <span><LifeBuoy size={14}/>现场处置进度</span>
        <h3>{recovered ? "车辆已恢复运营" : "系统正在持续处理车辆故障"}</h3>
      </div>
      <button type="button" onClick={operation.refresh} title="刷新处置进度" aria-label="刷新处置进度"><RefreshCw size={16}/></button>
    </header>
    <div className="driver-operation-summary">
      <section>
        <span><Truck size={17}/>道路救援</span>
        <strong>{rescueLabels[snapshot.rescue.status] ?? "救援状态同步中"}</strong>
        <div className="driver-operation-progress"><i style={{ width: snapshot.rescue.progress_percent + "%" }}/></div>
        <small>救援进度 {snapshot.rescue.progress_percent}% · {snapshot.rescue.rescue_unit_id}</small>
      </section>
      <section>
        <span><Wrench size={17}/>维修工单</span>
        <strong>{maintenanceSummary}</strong>
        <div className="driver-operation-progress is-repair"><i style={{ width: snapshot.maintenance.progress_percent + "%" }}/></div>
        <small>维修进度 {snapshot.maintenance.progress_percent}% · {snapshot.maintenance.bay_code ?? "工位待分配"}</small>
      </section>
      <section className="driver-operation-eta">
        <span><Clock3 size={17}/>预计恢复</span>
        <strong>{recovered ? "已完成" : snapshot.maintenance.countdown_seconds === null
          ? pendingEtaLabels[snapshot.maintenance.status] ?? "待评估"
          : <DriverCountdown
          key={snapshot.task_id + snapshot.generated_at}
          initialSeconds={snapshot.maintenance.countdown_seconds}
        />}</strong>
        <small>{operation.connected ? "状态每 3 秒自动同步" : "正在重新连接"}</small>
      </section>
    </div>
    <VehicleOperationTimeline snapshot={snapshot} context="employee"/>
    <footer><ShieldCheck size={16}/><span>维修完成并通过安全检查后，车辆会自动恢复为可调度状态。</span></footer>
  </article>;
}

function DriverCountdown({ initialSeconds }: { initialSeconds: number }) {
  const [seconds, setSeconds] = useState(initialSeconds);
  useEffect(() => {
    const timer = window.setInterval(() => setSeconds((value) => Math.max(0, value - 1)), 1000);
    return () => window.clearInterval(timer);
  }, []);
  return countdownLabel(seconds);
}
