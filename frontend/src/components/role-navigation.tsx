import { NavLink } from "react-router-dom";

import type { NavigationGroup } from "../navigation/navigation-model";

export function RoleNavigation({ groups, collapsed }: { groups: readonly NavigationGroup[]; collapsed: boolean }) {
  return <nav className="role-navigation" aria-label="主导航">
    {groups.map((group) => <section className="nav-group" aria-labelledby={`nav-group-${group.id}`} key={group.id}>
      {!collapsed ? <h2 id={`nav-group-${group.id}`}>{group.label}</h2> : <span id={`nav-group-${group.id}`} className="sr-only">{group.label}</span>}
      {group.items.map(({ id, label, secondaryLabel, route, icon: Icon }) => <NavLink
        key={id}
        to={route}
        aria-label={label}
        title={collapsed ? label : undefined}
        className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}
      >
        <Icon size={18} aria-hidden="true" />
        {!collapsed ? <span><strong>{label}</strong>{secondaryLabel ? <small>{secondaryLabel}</small> : null}</span> : null}
      </NavLink>)}
    </section>)}
  </nav>;
}
