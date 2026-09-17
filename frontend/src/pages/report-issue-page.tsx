import { useEffect, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Bot, CheckCircle2, RadioTower } from "lucide-react";

import { DriverRouteMap } from "../components/driver-route-map";
import { DriverOperationStatus } from "../components/driver-operation-status";
import { EmptyState } from "../components/ui/empty-state";
import { Skeleton } from "../components/ui/skeleton";
import { DataSourceBadge } from "../components/ui/data-source-badge";
import { StatusBadge } from "../components/ui/status-badge";
import { RoleWorkspaceFrame } from "../components/workspace/role-workspace-frame";
import { WorkspaceSection } from "../components/workspace/workspace-section";
import { createAnomalyReportSubmission, isTaskReportable } from "../features/anomaly-report/submission";
import {
  anomalyReferenceLabel,
  dispatchTaskReferenceLabel,
  fleetStatusMeta,
  reportSourceDisplayLabel,
  vehicleDisplayLabel,
} from "../features/fleet-sandbox/fleet-sandbox-data";
import { canonicalFleetVehicleId, fleetSimulationTick, fleetSnapshotByVehicleId } from "../features/fleet-sandbox/fleet-simulation";
import { useMyTasksRead } from "../hooks/use-workspace-reads";
import { anomalyReportClient } from "../services/api/anomaly-report-client";
import { ApiError } from "../services/api/client";
import type {
  AnomalyReportFormInput,
  AnomalyReportResponse,
  AnomalyReportSeverity,
  AnomalyReportType,
  ReportedVehicleStatus,
  RetryableAnomalyReportError,
} from "../types/anomaly-report";
import type { MyTaskListItem } from "../types/workspace-read-models";
import { localizeStatus } from "../utils/presentation-labels";

const anomalyTypeOptions: readonly [AnomalyReportType, string][] = [
  ["ROAD_HAZARD", "道路存在安全风险"],
  ["ROAD_BLOCKED", "道路阻断"],
  ["VEHICLE_BREAKDOWN", "车辆故障"],
  ["WEATHER", "天气影响"],
  ["CARGO", "货物异常"],
  ["CAPACITY", "运力问题"],
  ["OTHER", "其他问题"],
];

const vehicleStatusOptions: readonly [ReportedVehicleStatus, string][] = [
  ["NORMAL", "可正常行驶"],
  ["BROKEN", "故障，无法安全行驶"],
  ["UNAVAILABLE", "车辆不可用"],
  ["MAINTENANCE", "需要检修"],
];

const severityOptions: readonly [AnomalyReportSeverity, string][] = [
  ["LOW", "低"],
  ["MEDIUM", "中"],
  ["HIGH", "高"],
];

type DemoScenarioId = "VEHICLE_BREAKDOWN_N04" | "ROAD_BLOCKED_E04";

interface DemoScenario {
  id: DemoScenarioId;
  label: string;
  anomalyType: AnomalyReportType;
  description: string;
  locationText: string;
  vehicleStatus: ReportedVehicleStatus;
  severity: AnomalyReportSeverity;
  incidentNodeId: string | null;
  affectedEdgeId: string | null;
}

const demoScenarios: readonly DemoScenario[] = [
  {
    id: "VEHICLE_BREAKDOWN_N04",
    label: "车辆故障：当前车辆 · 新平路 K3.2",
    anomalyType: "VEHICLE_BREAKDOWN",
    description: "当前车辆在新平路 K3.2 发动机故障，无法继续配送。",
    locationText: "新平路 K3.2",
    vehicleStatus: "BROKEN",
    severity: "HIGH",
    incidentNodeId: "N04",
    affectedEdgeId: null,
  },
  {
    id: "ROAD_BLOCKED_E04",
    label: "道路堵塞：新平路东河桥段 · E04",
    anomalyType: "ROAD_BLOCKED",
    description: "新平路东河桥段发生塌方，车辆无法通行。",
    locationText: "新平路东河桥段",
    vehicleStatus: "NORMAL",
    severity: "HIGH",
    incidentNodeId: null,
    affectedEdgeId: "E04",
  },
];

function scenarioForRoute(scenario: DemoScenario, routeId: string | null | undefined): DemoScenario {
  if (scenario.id !== "ROAD_BLOCKED_E04" || routeId?.trim().toUpperCase() !== "ROUTE-03") return scenario;
  return {
    ...scenario,
    label: "道路堵塞：中心仓至 308 线 · E10",
    description: "中心仓至 308 线发生塌方，车辆需要绕行。",
    locationText: "中心仓至 308 线",
    affectedEdgeId: "E10",
  };
}

function retryableDetails(error: ApiError): RetryableAnomalyReportError | null {
  if (error.code !== "REPORT_QUEUE_UNAVAILABLE" || typeof error.details !== "object" || error.details === null) return null;
  const details = error.details as Partial<RetryableAnomalyReportError>;
  return typeof details.anomaly_id === "number"
    && typeof details.anomaly_no === "string"
    && typeof details.task_id === "string"
    && details.retryable === true
    ? {
        code: "REPORT_QUEUE_UNAVAILABLE",
        message: error.message,
        anomaly_id: details.anomaly_id,
        anomaly_no: details.anomaly_no,
        task_id: details.task_id,
        retryable: true,
      }
    : null;
}

function isDedicatedVehicleSource(task: MyTaskListItem): boolean {
  return task.task_id === "DEMO-TASK-REPORT-VEHICLE"
    || task.task_id === "DEMO-TASK-REPORT-ROAD"
    || task.task_id.startsWith("DEMO-TASK-REPORT-");
}

export function ReportIssuePage() {
  const [searchParams] = useSearchParams();
  const requestedTaskId = searchParams.get("taskId") ?? "";
  const [demoScenarioId, setDemoScenarioId] = useState<DemoScenarioId | "">("");
  const [anomalyType, setAnomalyType] = useState<AnomalyReportType>("ROAD_HAZARD");
  const [description, setDescription] = useState("");
  const [locationText, setLocationText] = useState("");
  const [vehicleStatus, setVehicleStatus] = useState<ReportedVehicleStatus>("NORMAL");
  const [severity, setSeverity] = useState<AnomalyReportSeverity>("MEDIUM");
  const [simulationTick, setSimulationTick] = useState(() => fleetSimulationTick());
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<AnomalyReportResponse | null>(null);
  const [savedFailure, setSavedFailure] = useState<RetryableAnomalyReportError | null>(null);
  const [retryInput, setRetryInput] = useState<AnomalyReportFormInput | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [submission] = useState(() => createAnomalyReportSubmission(anomalyReportClient));
  const read = useMyTasksRead({ limit: 100 });
  const reportableTasks = read.data?.items.filter((item) => item.can_report_anomaly && isTaskReportable(item.status)) ?? [];
  const vehicleTasks = reportableTasks.filter((task) => canonicalFleetVehicleId(task.vehicle_id));
  const fixedVehicleTask = vehicleTasks.find(isDedicatedVehicleSource) ?? null;
  const selectedVehicleId = canonicalFleetVehicleId(fixedVehicleTask?.vehicle_id);
  const selectedTask = vehicleTasks.find((task) => (
    task.task_id === requestedTaskId
    && canonicalFleetVehicleId(task.vehicle_id) === selectedVehicleId
  )) ?? fixedVehicleTask;
  const selectedVehicleSnapshot = fleetSnapshotByVehicleId(selectedVehicleId, simulationTick);
  const selectedRouteId = selectedTask?.original_route_id ?? selectedVehicleSnapshot?.routeId;
  const contextualDemoScenarios = demoScenarios.map((scenario) => scenarioForRoute(scenario, selectedRouteId));
  const activeDemoScenario = contextualDemoScenarios.find((scenario) => scenario.id === demoScenarioId) ?? null;
  const effectiveLocationText = activeDemoScenario?.locationText ?? selectedVehicleSnapshot?.locationLabel ?? locationText;
  const selectedTaskDisplay = selectedVehicleId
    ? reportSourceDisplayLabel(selectedVehicleId, selectedTask?.order_no)
    : "请先选择车辆";
  const operationTaskId = result?.task_id ?? "";

  useEffect(() => {
    const timer = window.setInterval(() => setSimulationTick(fleetSimulationTick()), 1500);
    return () => window.clearInterval(timer);
  }, []);

  const selectDemoScenario = (nextId: DemoScenarioId | "") => {
    setDemoScenarioId(nextId);
    const scenario = contextualDemoScenarios.find((item) => item.id === nextId);
    if (!scenario) return;
    setAnomalyType(scenario.anomalyType);
    setDescription(scenario.id === "VEHICLE_BREAKDOWN_N04" && selectedVehicleId
      ? `${vehicleDisplayLabel(selectedVehicleId)} 在新平路 K3.2 发动机故障，无法继续配送。`
      : scenario.description);
    setLocationText(scenario.locationText);
    setVehicleStatus(scenario.vehicleStatus);
    setSeverity(scenario.severity);
    setErrorMessage(null);
  };

  const changeAnomalyType = (nextType: AnomalyReportType) => {
    setAnomalyType(nextType);
    setVehicleStatus(nextType === "VEHICLE_BREAKDOWN" ? "BROKEN" : "NORMAL");
  };

  const submitInput = async (input: AnomalyReportFormInput) => {
    setSubmitting(true);
    setErrorMessage(null);
    try {
      const accepted = await submission.submit(input);
      setResult(accepted);
      setSavedFailure(null);
      setRetryInput(null);
    } catch (error) {
      if (error instanceof ApiError) {
        const saved = retryableDetails(error);
        setSavedFailure(saved);
        setRetryInput(saved ? input : null);
        setErrorMessage(error.message);
      } else {
        setRetryInput(null);
        setErrorMessage("问题暂时无法提交，请稍后重试。不会回退到演示数据。");
      }
    } finally {
      setSubmitting(false);
    }
  };

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selectedTask) {
      setErrorMessage("当前固定车辆没有可上报的进行中配送任务。");
      return;
    }
    void submitInput({
      source_task_id: selectedTask.task_id,
      anomaly_type: anomalyType,
      description,
      location_text: effectiveLocationText,
      reported_vehicle_status: vehicleStatus,
      severity,
      incident_node_id: activeDemoScenario ? activeDemoScenario.incidentNodeId : selectedVehicleSnapshot?.nodeId ?? null,
      affected_edge_id: activeDemoScenario?.affectedEdgeId ?? null,
    });
  };

  return <RoleWorkspaceFrame
    title="提出配送问题"
    description="从本人进行中的配送任务上报真实问题，提交后会立即启动 AI 异常识别与调度。"
    actions={<div className="workspace-action-cluster">{read.data ? <DataSourceBadge provenance={read.data.provenance} detail="本人任务与车辆绑定来自后端 API"/> : null}<Link className="secondary-action" to="/my-tasks">返回我的任务</Link></div>}
  >
    <WorkspaceSection id="report-task-context" title="当前配送任务" description="系统按当前员工账号锁定固定车辆，并同步关联进行中的运单、路线和位置。">
      {read.state === "LOADING" ? <Skeleton label="正在读取本人任务" lines={3} /> : null}
      {read.state === "READY" && read.data ? <div className="report-task-context">
        <label htmlFor="report-source-task">当前任务
          <input id="report-source-task" value={selectedTaskDisplay} readOnly aria-readonly="true" />
        </label>
        <label htmlFor="report-vehicle">固定车辆
          <input id="report-vehicle" value={selectedVehicleId ? vehicleDisplayLabel(selectedVehicleId) : "暂无固定车辆"} readOnly aria-readonly="true" />
          <small className="report-fixed-vehicle-note">车辆由调度中心与当前员工账号绑定，员工端不可切换。</small>
        </label>
        <label htmlFor="report-route">配送路线
          <input id="report-route" value={selectedVehicleSnapshot?.routeDisplayName ?? "请先选择车辆"} readOnly aria-readonly="true" />
        </label>
        {selectedTask ? <dl className="report-task-facts">
          <div><dt>运单</dt><dd>运单-{selectedVehicleId ? selectedVehicleId.slice(-3) : "—"}</dd></div>
          <div><dt>车辆</dt><dd>{vehicleDisplayLabel(selectedVehicleId)}</dd></div>
          <div><dt>配送方向</dt><dd>{selectedTask.origin ?? "—"} → {selectedTask.destination ?? "—"}</dd></div>
          <div><dt>任务状态</dt><dd><StatusBadge status={selectedTask.status} label={localizeStatus(selectedTask.status)} /></dd></div>
        </dl> : null}
      </div> : null}
      {read.state !== "LOADING" && read.state !== "READY" ? <EmptyState
        kind={read.state === "FORBIDDEN" ? "forbidden" : "unavailable"}
        title={read.state === "EMPTY" ? "当前没有可上报的配送任务" : "本人任务暂时无法读取"}
        description="请返回我的任务刷新后再试；系统不会使用静态任务代替。"
        action={<button type="button" onClick={read.refresh}>重新读取</button>}
      /> : null}
    </WorkspaceSection>

    <WorkspaceSection id="report-route-position" title="车辆与路线位置" description="地图只展示当前车辆所在路线及沿线站点，位置与管理员沙盘同步。">
      {selectedVehicleSnapshot
        ? <DriverRouteMap vehicle={selectedVehicleSnapshot}/>
        : <EmptyState kind="empty" title="暂无固定车辆" description="请联系调度中心为当前员工绑定车辆和进行中的配送任务。" />}
    </WorkspaceSection>

    {operationTaskId ? <WorkspaceSection id="driver-operation-progress" title="救援与维修进度" description="只读展示当前任务处置状态；救援调度、维修和质检由调度中心与系统自动执行。">
      <DriverOperationStatus taskId={operationTaskId}/>
    </WorkspaceSection> : null}

    <WorkspaceSection id="driver-anomaly-report" title="问题信息" description="请填写现场真实情况。首版不采集照片和 GPS。">
      <form className="anomaly-report-form" onSubmit={onSubmit}>
        <fieldset disabled={read.state !== "READY" || !selectedTask || submitting || Boolean(savedFailure) || Boolean(result)}>
          <div className="report-form-grid">
            <label className="report-scenario-field" htmlFor="report-demo-scenario">演示异常场景
              <select id="report-demo-scenario" value={demoScenarioId} onChange={(event) => selectDemoScenario(event.target.value as DemoScenarioId | "")}>
                <option value="">手动填写现场问题</option>
                {contextualDemoScenarios.map((scenario) => <option key={scenario.id} value={scenario.id}>{scenario.label}</option>)}
              </select>
            </label>
            <label htmlFor="report-anomaly-type">问题类型
              <select id="report-anomaly-type" value={anomalyType} disabled={Boolean(activeDemoScenario)} onChange={(event) => changeAnomalyType(event.target.value as AnomalyReportType)}>
                {anomalyTypeOptions.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>
            <label htmlFor="report-vehicle-status">车辆状态
              <select id="report-vehicle-status" value={vehicleStatus} disabled={Boolean(activeDemoScenario)} onChange={(event) => setVehicleStatus(event.target.value as ReportedVehicleStatus)}>
                {vehicleStatusOptions.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>
            <label htmlFor="report-severity">风险等级
              <select id="report-severity" value={severity} disabled={Boolean(activeDemoScenario)} onChange={(event) => setSeverity(event.target.value as AnomalyReportSeverity)}>
                {severityOptions.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>
            <label htmlFor="report-location">当前位置
              {activeDemoScenario
                ? <select id="report-location" value={locationText} onChange={(event) => setLocationText(event.target.value)} required>
                    <option value={activeDemoScenario.locationText}>{activeDemoScenario.locationText}</option>
                  </select>
                : <input id="report-location" value={effectiveLocationText} readOnly={Boolean(selectedVehicleSnapshot)} onChange={(event) => setLocationText(event.target.value)} minLength={1} maxLength={255} required />}
              {selectedVehicleSnapshot ? <small className="report-vehicle-location-note">车辆位置来自管理员地图同一套虚拟沙盘 · {selectedVehicleSnapshot.routeDisplayName} · {fleetStatusMeta[selectedVehicleSnapshot.status].label}</small> : null}
            </label>
            <label className="report-description-field" htmlFor="report-description">问题描述
              <textarea id="report-description" value={description} readOnly={Boolean(activeDemoScenario)} onChange={(event) => setDescription(event.target.value)} minLength={5} maxLength={2000} rows={5} required />
            </label>
          </div>
          <div className="report-submit-row">
            <p>提交后系统会保存异常，并通过现有 8-Agent 流程异步生成调度建议。</p>
            <button className="primary-action" type="submit" disabled={!selectedTask || submitting}>{submitting ? "正在提交…" : "提交问题并启动 AI 调度"}</button>
          </div>
        </fieldset>
      </form>

      {errorMessage ? <div className="report-feedback report-feedback--error" role="alert">
        <strong>{savedFailure ? "问题已保存，但 AI 调度暂未启动" : "提交未完成"}</strong>
        <p>{errorMessage}</p>
        {savedFailure ? <>
          <p>{anomalyReferenceLabel(savedFailure.anomaly_id, savedFailure.anomaly_no)} · {dispatchTaskReferenceLabel(savedFailure.task_id, savedFailure.anomaly_id)}</p>
          <button type="button" disabled={submitting} onClick={() => { if (retryInput) void submitInput(retryInput); }}>重试启动 AI 调度</button>
        </> : null}
      </div> : null}

      {result ? <div className="report-feedback report-feedback--success" role="status">
        <strong>{result.message}</strong>
        <p>{anomalyReferenceLabel(result.anomaly_id, result.anomaly_no)} · {dispatchTaskReferenceLabel(result.task_id, result.anomaly_id)}</p>
        <ol className="report-sync-steps" data-driver-sync-state="ACCEPTED" aria-label="问题同步状态">
          <li className="is-complete"><CheckCircle2 size={17}/><span><strong>后端已接收</strong><small>异常与任务编号已保存</small></span></li>
          <li className="is-active"><Bot size={17}/><span><strong>AI 调度已启动</strong><small>正在生成处置与路线方案</small></span></li>
          <li><RadioTower size={17}/><span><strong>管理端将在 1 秒内同步</strong><small>调度中心会自动定位当前车辆</small></span></li>
        </ol>
        <div className="report-result-actions">
          <Link className="primary-action" to={`/dispatch/${result.task_id}`}>查看 AI 调度进度</Link>
          <Link className="secondary-action" to="/my-tasks">返回我的任务</Link>
        </div>
      </div> : null}
    </WorkspaceSection>
  </RoleWorkspaceFrame>;
}
