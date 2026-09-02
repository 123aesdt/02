import { useState } from "react";
import { localizeStatus } from "../utils/presentation-labels";

export function MockRuntimeInterventionWorkbench() {
  const [applied, setApplied] = useState(false);
  return <section className="runtime-intervention-panel" data-source="mock"><p className="eyebrow">演示数据 · 隔离环境</p><h2>运行态干预</h2><p>车辆 vehicle-001 · {localizeStatus(applied ? "BROKEN" : "NORMAL")} · 版本 {applied ? 8 : 7}</p><button data-target="BROKEN" onClick={() => setApplied(true)}>故障</button>{applied ? <p>演示操作已应用 · 正常 → 故障 · V7 → V8</p> : null}</section>;
}
