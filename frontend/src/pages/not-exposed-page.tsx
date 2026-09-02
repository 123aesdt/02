import { EmptyState } from "../components/ui/empty-state";
import { RoleWorkspaceFrame } from "../components/workspace/role-workspace-frame";

export function NotExposedPage({ title, message }: { title: string; message: string }) {
  return <RoleWorkspaceFrame title={title} description="此页面只会接入已批准并由后端支持的安全读取契约。">
    <EmptyState kind="not-exposed" title={message} description="CountyFlow 不会用静态数组或 Mock 回退掩盖缺失的 API。" />
  </RoleWorkspaceFrame>;
}
