import type { ReactNode } from "react";

export function RoleWorkspaceFrame({ title, description, actions, children }: {
  title: string;
  description: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return <div className="role-workspace">
    <header className="role-workspace__heading">
      <div><h1>{title}</h1><p>{description}</p></div>
      {actions ? <div className="role-workspace__actions">{actions}</div> : null}
    </header>
    {children}
  </div>;
}
