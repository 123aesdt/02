import { AdminOverviewDashboard } from "../components/admin-overview-dashboard";
import { EmptyState } from "../components/ui/empty-state";
import { Skeleton } from "../components/ui/skeleton";
import { RoleWorkspaceFrame } from "../components/workspace/role-workspace-frame";
import { WorkspaceSection } from "../components/workspace/workspace-section";
import { runtimeConfig } from "../config/runtime";
import { useOverview } from "../hooks/use-workspace-reads";
import type { WorkspaceReadProvenance } from "../types/workspace-read-models";

function provenanceLabel(provenance: WorkspaceReadProvenance) { return provenance === "LIVE" ? "实时数据" : provenance === "MIXED" ? "混合数据" : "演示数据"; }

function OverviewReadFeedback({ state, onRetry }: { state: string; onRetry: () => void }) {
  if (state === "LOADING") return <Skeleton label="正在加载系统总览" lines={4} />;
  if (state === "FORBIDDEN") return <EmptyState kind="forbidden" title="没有查看系统总览的权限" />;
  if (state === "UNAVAILABLE") return <EmptyState kind="unavailable" title="服务暂不可用" description="请稍后重试。" action={<button type="button" onClick={onRetry}>重试</button>} />;
  return <EmptyState kind="error" title="系统总览加载失败" description="请重试后再查看。" action={<button type="button" onClick={onRetry}>重试</button>} />;
}

export function AdminOverviewPage() {
  const read = useOverview();
  if (runtimeConfig.dataMode === "api") {
    if (read.state !== "READY") return <RoleWorkspaceFrame title="系统总览" description="从统一产品视角进入业务、智能体、记忆、运行、可观测性与治理中心。"><WorkspaceSection id="admin-summary" title="产品能力总览" description="正在读取已开放的领域计数。"><OverviewReadFeedback state={read.state} onRetry={read.refresh} /></WorkspaceSection></RoleWorkspaceFrame>;
    const source = provenanceLabel(read.data.provenance);
    return <RoleWorkspaceFrame title="系统总览" description="从统一产品视角进入业务、智能体、记忆、运行、可观测性与治理中心。">
      <p className="admin-overview-source-note">实时计数与演示摘要；虚拟内容均已单独标识。</p>
      <AdminOverviewDashboard data={read.data} sourceLabel={source} />
    </RoleWorkspaceFrame>;
  }
  return <RoleWorkspaceFrame title="系统总览" description="从统一产品视角进入业务、智能体、记忆、运行、可观测性与治理中心。"><WorkspaceSection id="admin-summary" title="产品能力总览" description="当前运行模式未开放系统总览接口。"><OverviewReadFeedback state="UNAVAILABLE" onRetry={read.refresh} /></WorkspaceSection></RoleWorkspaceFrame>;
}
