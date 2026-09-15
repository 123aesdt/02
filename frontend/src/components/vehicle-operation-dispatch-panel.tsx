import { Radio, RefreshCw } from "lucide-react";

import { demoVehicleOperationSnapshot } from "../features/fleet-sandbox/vehicle-operation-demo";
import { useVehicleOperationSnapshot } from "../hooks/use-vehicle-operation-snapshot";
import { VehicleCommandCenter } from "./vehicle-command-center";


export function VehicleOperationDispatchPanel({ taskId }: { taskId: string }) {
  const fallback = taskId === demoVehicleOperationSnapshot.task_id ? demoVehicleOperationSnapshot : null;
  const state = useVehicleOperationSnapshot(taskId, fallback);

  return <section
    className="vehicle-command-page dispatch-vehicle-operation"
    data-vehicle-operation-dispatch={taskId}
    aria-labelledby="vehicle-operation-dispatch-title"
  >
    <div className="vehicle-command-pagebar">
      <div>
        <span><Radio size={13}/>当前调度 · {taskId}</span>
        <strong id="vehicle-operation-dispatch-title">故障救援与维修执行态势</strong>
      </div>
      <button type="button" onClick={state.refresh}><RefreshCw size={14}/>刷新处置进度</button>
    </div>
    {state.snapshot
      ? <VehicleCommandCenter snapshot={state.snapshot} connection={state.connection}/>
      : <div className="operation-dispatch-empty" role={state.error ? "alert" : "status"}>
        <strong>{state.loading ? "正在读取救援维修记录" : "暂无救援维修记录"}</strong>
        <span>{state.error ?? "系统正在等待该调度任务生成车辆救援与维修工单。"}</span>
      </div>}
  </section>;
}
