import { Check, Clock3 } from "lucide-react";

import type { VehicleOperationSnapshot } from "../types/vehicle-operations";

type VehicleOperationTimelineProps = {
  snapshot: VehicleOperationSnapshot;
  context: "dispatcher" | "employee";
};

const stageStatusLabel = {
  COMPLETED: "已完成",
  ACTIVE: "进行中",
  WAITING: "待执行",
  FAILED: "失败",
  CANCELLED: "已取消",
  SKIPPED: "无需执行",
} as const;

function maintenanceEtaLabel(snapshot: VehicleOperationSnapshot, recovered: boolean) {
  if (recovered) return "已恢复运营";
  if (snapshot.maintenance.countdown_seconds !== null && snapshot.maintenance.countdown_seconds > 0) {
    return `${snapshot.maintenance.countdown_seconds} 秒`;
  }
  return {
    SCHEDULED: "等待车辆到站",
    WAITING_BAY: "等待进入工位",
    DIAGNOSING: "诊断后生成",
    QA_PENDING: "等待安全质检",
    FAILED: "处置失败",
    CANCELLED: "工单已取消",
  }[snapshot.maintenance.status] ?? "预计时间待生成";
}

export function VehicleOperationTimeline({ snapshot, context }: VehicleOperationTimelineProps) {
  const recovered = snapshot.incident.status === "RECOVERED";
  return <section
    className={`vehicle-operation-timeline ${context === "dispatcher" ? "fleet-operation-lifecycle" : "is-employee"}`}
    data-vehicle-operation-timeline
    data-context={context}
    data-operation-lifecycle={context === "dispatcher" ? true : undefined}
  >
    {context === "dispatcher" ? <header>
      <strong><Clock3 size={16}/>自主处置时间线</strong>
      <span>{snapshot.rescue.mission_no}</span>
    </header> : null}
    <ol className={context === "employee" ? "driver-operation-stages" : undefined}>
      {snapshot.stages.map((stage) => <li key={stage.key} data-operation-stage={stage.key} className={`is-${stage.status.toLowerCase()}`}>
        <i>{stage.status === "COMPLETED" ? <Check size={13}/> : null}</i>
        <span><strong>{stage.title}</strong><small>{stage.detail}</small></span>
        <em>{stageStatusLabel[stage.status]}</em>
      </li>)}
    </ol>
    {snapshot.timeline.length ? <div className="vehicle-operation-events" aria-label="处置事件">
      {snapshot.timeline.map((event) => <span key={event.event_id}>
        <time dateTime={event.timestamp}>{event.timestamp}</time><strong>{event.label}</strong>
      </span>)}
    </div> : null}
    {context === "dispatcher" ? <div className="fleet-operation-maintenance">
      <span>{recovered ? "车辆已自动复岗" : `维修进度 ${snapshot.maintenance.progress_percent}%`}</span>
      <strong>{maintenanceEtaLabel(snapshot, recovered)}</strong>
    </div> : null}
  </section>;
}
