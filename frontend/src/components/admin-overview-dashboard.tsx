import {
  Activity,
  ArrowUpRight,
  BarChart3,
  Bot,
  Boxes,
  ChevronRight,
  CircleCheck,
  ClipboardCheck,
  Database,
  PackageCheck,
  ShieldCheck,
  Sparkles,
  TriangleAlert,
  Workflow,
  type LucideIcon,
} from "lucide-react";
import { Link } from "react-router-dom";

import { demoCapabilitySummaries } from "../demo/demo-snapshots";
import type { OverviewResponse } from "../types/workspace-read-models";
import { StatusBadge } from "./ui/status-badge";

type OverviewTone = "blue" | "cyan" | "violet" | "amber" | "rose";

const trendBars = [30, 44, 37, 58, 49, 67, 54, 78, 65, 88];

function OverviewKpi({ id, label, value, note, tone, icon: Icon }: {
  id: string;
  label: string;
  value: number;
  note: string;
  tone: OverviewTone;
  icon: LucideIcon;
}) {
  return <article className={`admin-overview-kpi tone-${tone}`} data-overview-kpi={id}>
    <span className="admin-overview-kpi__icon"><Icon aria-hidden="true" /></span>
    <div className="admin-overview-kpi__copy"><span>{label}</span><strong>{value}</strong><small>{note}</small></div>
    <div className="admin-overview-kpi__trend" aria-hidden="true">
      {trendBars.map((height, index) => <i key={`${id}-${index}`} style={{ height: `${height}%` }} />)}
    </div>
    <span className="admin-overview-kpi__source">接口返回计数 <ChevronRight aria-hidden="true" /></span>
  </article>;
}

interface CapabilityDefinition {
  title: string;
  route: string;
  tone: OverviewTone;
  icon: LucideIcon;
  value: string;
  valueLabel: string;
  detail: string;
  source: "live" | "demo";
  rows: readonly [string, string][];
}

function CapabilityCard({ capability, sourceLabel, sourceStatus }: {
  capability: CapabilityDefinition;
  sourceLabel: string;
  sourceStatus: string;
}) {
  const Icon = capability.icon;
  return <article className={`admin-overview-capability tone-${capability.tone}`} data-overview-capability>
    <header>
      <span className="admin-overview-capability__icon"><Icon aria-hidden="true" /></span>
      <div><Link to={capability.route}>{capability.title}</Link><p>{capability.detail}</p></div>
      <span className="admin-overview-capability__arrow"><ChevronRight aria-hidden="true" /></span>
    </header>
    <div className="admin-overview-capability__body">
      <div className="admin-overview-capability__value"><strong>{capability.value}</strong><span>{capability.valueLabel}</span></div>
      <div className="admin-overview-capability__bars" aria-hidden="true">
        {trendBars.slice(1, 9).map((height, index) => <i key={index} style={{ height: `${height}%` }} />)}
      </div>
      <ul>{capability.rows.map(([label, value]) => <li key={label}><span><CircleCheck aria-hidden="true" />{label}</span><b>{value}</b></li>)}</ul>
    </div>
    <StatusBadge status={capability.source === "live" ? sourceStatus : "DEMO"} label={capability.source === "live" ? sourceLabel : "演示数据"} />
  </article>;
}

export function AdminOverviewDashboard({ data, sourceLabel }: { data: OverviewResponse; sourceLabel: string }) {
  const capabilities: readonly CapabilityDefinition[] = [
    {
      title: "业务健康", route: "/anomalies", tone: "cyan", icon: BarChart3,
      value: `${data.orders}/${data.anomalies}`, valueLabel: "运单 / 异常", detail: "接口领域计数已接入。", source: "live",
      rows: [["接口服务", "正常"], ["数据同步", "已连接"], ["核心流程", "运行中"]],
    },
    {
      title: "智能体", route: "/agents", tone: "blue", icon: Bot,
      value: "8", valueLabel: "智能体数量", detail: demoCapabilitySummaries.智能体, source: "demo",
      rows: [["任务规划", "就绪"], ["路径调度", "就绪"], ["异常分析", "就绪"]],
    },
    {
      title: "记忆", route: "/memory", tone: "violet", icon: Database,
      value: "50", valueLabel: "向量记录", detail: demoCapabilitySummaries.记忆, source: "demo",
      rows: [["向量记忆", "50"], ["关系事实", "24"], ["知识图谱", "可用"]],
    },
    {
      title: "运行", route: "/runtime", tone: "cyan", icon: Activity,
      value: String(data.runtime_threads), valueLabel: "运行线程", detail: "线程、Checkpoint 与任务级治理入口。", source: "live",
      rows: [["任务执行", "正常"], ["调度引擎", "正常"], ["消息队列", "正常"]],
    },
    {
      title: "可观测性", route: "/monitor", tone: "amber", icon: BarChart3,
      value: "11", valueLabel: "遥测指标", detail: demoCapabilitySummaries.可观测性, source: "demo",
      rows: [["链路追踪", "已接入"], ["性能监控", "已接入"], ["日志分析", "已接入"]],
    },
    {
      title: "治理与安全", route: "/audit", tone: "rose", icon: ShieldCheck,
      value: "32", valueLabel: "审计样本", detail: demoCapabilitySummaries.治理与安全, source: "demo",
      rows: [["权限管控", "正常"], ["操作审计", "正常"], ["风险识别", "正常"]],
    },
  ];

  return <section className="admin-overview-dashboard" data-admin-overview-dashboard>
    <div className="admin-overview-kpis" aria-label="核心业务指标">
      <OverviewKpi id="orders" label="运单" value={data.orders} note="当前接口快照" tone="blue" icon={PackageCheck} />
      <OverviewKpi id="anomalies" label="异常" value={data.anomalies} note="当前待处置范围" tone="rose" icon={TriangleAlert} />
      <OverviewKpi id="reviews" label="待复核" value={data.reviews} note="当前审核队列" tone="cyan" icon={ClipboardCheck} />
      <OverviewKpi id="runtime" label="运行线程" value={data.runtime_threads} note="当前运行状态" tone="violet" icon={Workflow} />
    </div>

    <div className="admin-overview-heading">
      <h2><Sparkles aria-hidden="true" />功能模块</h2>
      <p>“ 以数据驱动决策，用智能重塑县域物流。 ”</p>
    </div>

    <div className="admin-overview-capabilities">
      {capabilities.map((capability) => <CapabilityCard
        key={capability.route}
        capability={capability}
        sourceLabel={sourceLabel}
        sourceStatus={data.provenance}
      />)}
    </div>

    <footer className="admin-overview-footer" data-overview-footer>
      <div className="admin-overview-footer__brand"><Boxes aria-hidden="true" /><span><strong>县域物流数字化新范式</strong><small>数据连接县域 · 智能调度未来</small></span></div>
      <div className="admin-overview-footer__stats">
        <span><strong>{data.orders}</strong><small>当前运单</small></span>
        <span><strong>{data.runtime_threads}</strong><small>运行线程</small></span>
        <span><strong>{data.anomalies}</strong><small>当前异常</small></span>
      </div>
      <p>科技让县域更美好 <ArrowUpRight aria-hidden="true" /></p>
    </footer>
  </section>;
}
