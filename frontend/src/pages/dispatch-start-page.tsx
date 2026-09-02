import { BrainCircuit, CircleAlert, Route as RouteIcon, ShieldCheck } from "lucide-react";

import { DispatchSubmissionButton } from "../components/dispatch-submission-button";

const steps = [
  ["异常接入", "校验异常信息并规范化上下文", CircleAlert],
  ["8-Agent 协作", "记忆、环境、运力、路径、调度与审核依次执行", BrainCircuit],
  ["结果持久化", "写入调度与审计事实，并推送实时事件", ShieldCheck],
];

export function DispatchStartPage() {
  return <div className="workspace-page"><section className="workspace-panel"><div className="panel-heading"><div><p className="eyebrow">实时智能调度</p><h2>发起一项新的调度任务</h2></div><RouteIcon size={20}/></div><p className="description">将以“李师傅 · 新平路 · 雨天道路湿滑”核心案例提交真实异步任务；完成后自动进入可回放的任务详情。</p><DispatchSubmissionButton/></section><section className="workspace-panel"><div className="panel-heading"><div><p className="eyebrow">处理流程</p><h2>任务将经历什么</h2></div></div><div className="detail-list">{steps.map(([title, detail, Icon]) => { const StepIcon = Icon as typeof CircleAlert; return <span key={title as string}><StepIcon size={16}/><strong>{title as string}</strong><small>{detail as string}</small></span>; })}</div></section></div>;
}
