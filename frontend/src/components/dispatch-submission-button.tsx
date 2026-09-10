import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { FIXED_DEMO_EMPLOYEES } from "../auth/demo-employees";

import { coreRainDispatch, createDispatchSubmission } from "../features/dispatch/submission";
import { taskStateCopy } from "../features/dispatch/task-state";
import { runtimeConfig } from "../config/runtime";
import { ApiError } from "../services/api/client";
import { createDispatchTask } from "../services/dispatch-service";

const fixedDeliveryEmployees = FIXED_DEMO_EMPLOYEES.filter((employee) => employee.role === "EMPLOYEE");

export function DispatchSubmissionButton() {
  const navigate = useNavigate();
  const submission = useRef(createDispatchSubmission(createDispatchTask));
  const [selectedAssignee, setSelectedAssignee] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const assigneeEmployeeId = selectedAssignee || fixedDeliveryEmployees[0].employee_id;

  const submit = async () => {
    if (submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      if (runtimeConfig.dataMode === "mock") {
        navigate("/dispatch/TASK-20260821-0042");
        return;
      }
      if (!assigneeEmployeeId) {
        setError("请选择接收员工后再发起调度。");
        return;
      }
      const response = await submission.current.submit({
        ...coreRainDispatch,
        assignee_employee_id: assigneeEmployeeId,
      });
      navigate(`/dispatch/${response.task_id}`);
    } catch (reason) {
      const code = reason instanceof ApiError ? reason.code : "BACKEND_OFFLINE";
      setError(taskStateCopy(code).description);
    } finally {
      setSubmitting(false);
    }
  };

  return <div className="dispatch-submit">{runtimeConfig.dataMode === "api" ? <label className="dispatch-recipient"><span>接收员工</span><select aria-label="接收员工" value={assigneeEmployeeId} disabled={submitting} onChange={(event) => setSelectedAssignee(event.target.value)}>{fixedDeliveryEmployees.map((employee) => <option key={employee.employee_id} value={employee.employee_id}>{employee.display_name} · 配送员工</option>)}</select></label> : null}<button className="button-primary" disabled={submitting} onClick={() => void submit()}>{submitting ? "正在提交…" : "发起 AI 调度"}</button>{error && <p role="alert" className="error-banner">{error}</p>}</div>;
}
