import { Radio, RefreshCw } from "lucide-react";

import { VehicleCommandCenter } from "../components/vehicle-command-center";
import { demoVehicleOperationSnapshot } from "../features/fleet-sandbox/vehicle-operation-demo";
import { useVehicleOperationSnapshot } from "../hooks/use-vehicle-operation-snapshot";


export function VehicleCommandCenterPage() {
  const state = useVehicleOperationSnapshot(demoVehicleOperationSnapshot.task_id, demoVehicleOperationSnapshot);
  if (!state.snapshot) return null;
  return <div className="vehicle-command-page">
    <div className="vehicle-command-pagebar">
      <div><span><Radio size={13}/>车辆态势地图 · 县域车辆运营中枢</span><strong>故障车辆救援与维修联动</strong></div>
      <button type="button" onClick={state.refresh}><RefreshCw size={14}/>刷新态势</button>
    </div>
    <VehicleCommandCenter snapshot={state.snapshot} connection={state.connection}/>
  </div>;
}
