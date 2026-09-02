import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { EmptyState } from "../components/ui/empty-state";
import { Skeleton } from "../components/ui/skeleton";
import { StatusBadge } from "../components/ui/status-badge";
import { RoleWorkspaceFrame } from "../components/workspace/role-workspace-frame";
import { WorkspaceSection } from "../components/workspace/workspace-section";
import { createAnomalyReportSubmission, isTaskReportable } from "../features/anomaly-report/submission";
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

export function ReportIssuePage() {
  const [searchParams] = useSearchParams();
  const [selectedTaskId, setSelectedTaskId] = useState(() => searchParams.get("taskId") ?? "");
  const [anomalyType, setAnomalyType] = useState<AnomalyReportType>("ROAD_HAZARD");
  const [description, setDescription] = useState("");
  const [locationText, setLocationText] = useState("");
  const [vehicleStatus, setVehicleStatus] = useState<ReportedVehicleStatus>("NORMAL");
  const [severity, setSeverity] = useState<AnomalyReportSeverity>("MEDIUM");
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<AnomalyReportResponse | null>(null);
  const [savedFailure, setSavedFailure] = useState<RetryableAnomalyReportError | null>(null);
  const [retryInput, setRetryInput] = useState<AnomalyReportFormInput | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [submission] = useState(() => createAnomalyReportSubmission(anomalyReportClient));
  const read = useMyTasksRead({ limit: 100 });
  const reportableTasks = read.data?.items.filter((item) => isTaskReportable(item.status)) ?? [];
  const selectedTask = read.data?.items.find((item) => item.task_id === selectedTaskId) ?? null;

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
    if (!selectedTaskId) {
      setErrorMessage("请选择一项进行中的配送任务。");
      return;
    }
    void submitInput({
      source_task_id: selectedTaskId,
      anomaly_type: anomalyType,
      description,
      location_text: locationText,
      reported_vehicle_status: vehicleStatus,
      severity,
    });
  };

  return <RoleWorkspaceFrame
    title="提出配送问题"
    description="从本人进行中的配送任务上报真实问题，提交后会立即启动 AI 异常识别与调度。"
    actions={<Link className="secondary-action" to="/my-tasks">返回我的任务</Link>}
  >
    <WorkspaceSection id="report-task-context" title="当前配送任务" description="订单、司机、车辆和路线由服务端根据本人任务推导，无法在此修改。">
      {read.state === "LOADING" ? <Skeleton label="正在读取本人任务" lines={3} /> : null}
      {read.state === "READY" && read.data ? <div className="report-task-context">
        <label htmlFor="report-source-task">当前任务
          <select id="report-source-task" value={selectedTaskId} onChange={(event) => setSelectedTaskId(event.target.value)} required disabled={submitting || Boolean(savedFailure)}>
            <option value="">请选择进行中的任务</option>
            {reportableTasks.map((task) => <option key={task.task_id} value={task.task_id}>{task.task_id} · {task.order_no ?? "未绑定运单"}</option>)}
          </select>
        </label>
        {selectedTask ? <dl className="report-task-facts">
          <div><dt>运单</dt><dd>{selectedTask.order_no ?? "—"}</dd></div>
          <div><dt>车辆</dt><dd>{selectedTask.vehicle_id ?? "—"}</dd></div>
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

    <WorkspaceSection id="driver-anomaly-report" title="问题信息" description="请填写现场真实情况。首版不采集照片和 GPS。">
      <form className="anomaly-report-form" onSubmit={onSubmit}>
        <fieldset disabled={submitting || Boolean(savedFailure) || Boolean(result)}>
          <div className="report-form-grid">
            <label htmlFor="report-anomaly-type">问题类型
              <select id="report-anomaly-type" value={anomalyType} onChange={(event) => setAnomalyType(event.target.value as AnomalyReportType)}>
                {anomalyTypeOptions.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>
            <label htmlFor="report-vehicle-status">车辆状态
              <select id="report-vehicle-status" value={vehicleStatus} onChange={(event) => setVehicleStatus(event.target.value as ReportedVehicleStatus)}>
                {vehicleStatusOptions.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>
            <label htmlFor="report-severity">风险等级
              <select id="report-severity" value={severity} onChange={(event) => setSeverity(event.target.value as AnomalyReportSeverity)}>
                {severityOptions.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>
            <label htmlFor="report-location">当前位置
              <input id="report-location" value={locationText} onChange={(event) => setLocationText(event.target.value)} minLength={1} maxLength={255} required />
            </label>
            <label className="report-description-field" htmlFor="report-description">问题描述
              <textarea id="report-description" value={description} onChange={(event) => setDescription(event.target.value)} minLength={5} maxLength={2000} rows={5} required />
            </label>
          </div>
          <div className="report-submit-row">
            <p>提交后系统会保存异常，并通过现有 8-Agent 流程异步生成调度建议。</p>
            <button className="primary-action" type="submit" disabled={!selectedTaskId || submitting}>{submitting ? "正在提交…" : "提交问题并启动 AI 调度"}</button>
          </div>
        </fieldset>
      </form>

      {errorMessage ? <div className="report-feedback report-feedback--error" role="alert">
        <strong>{savedFailure ? "问题已保存，但 AI 调度暂未启动" : "提交未完成"}</strong>
        <p>{errorMessage}</p>
        {savedFailure ? <>
          <p>异常：{savedFailure.anomaly_no} · 任务：{savedFailure.task_id}</p>
          <button type="button" disabled={submitting} onClick={() => { if (retryInput) void submitInput(retryInput); }}>重试启动 AI 调度</button>
        </> : null}
      </div> : null}

      {result ? <div className="report-feedback report-feedback--success" role="status">
        <strong>{result.message}</strong>
        <p>异常：{result.anomaly_no} · 调度任务：{result.task_id}</p>
        <div className="report-result-actions">
          <Link className="primary-action" to={`/dispatch/${result.task_id}`}>查看 AI 调度进度</Link>
          <Link className="secondary-action" to="/my-tasks">返回我的任务</Link>
        </div>
      </div> : null}
    </WorkspaceSection>
  </RoleWorkspaceFrame>;
}
