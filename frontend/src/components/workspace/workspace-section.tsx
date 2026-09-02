import { useId, type ReactNode } from "react";

export interface WorkspaceSectionProps {
  id?: string;
  title: string;
  description?: string;
  actions?: ReactNode;
  children: ReactNode;
}

export function WorkspaceSection({ id, title, description, actions, children }: WorkspaceSectionProps) {
  const generatedId = useId().replace(/:/g, "");
  const headingId = `workspace-section-${id ?? generatedId}`;

  return <section className="workspace-section" aria-labelledby={headingId}>
    <header className="workspace-section__header">
      <div>
        <h2 id={headingId}>{title}</h2>
        {description ? <p>{description}</p> : null}
      </div>
      {actions ? <div className="workspace-section__actions">{actions}</div> : null}
    </header>
    <div className="workspace-section__body">{children}</div>
  </section>;
}
