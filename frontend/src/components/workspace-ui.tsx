import { X } from "lucide-react";
import type { ReactNode } from "react";
import { localizeStatus } from "../utils/presentation-labels";

export function Metric({ label, value, note, tone = "" }: { label: string; value: string; note: string; tone?: string }) { return <article className={`metric ${tone}`}><p>{label}</p><strong>{value}</strong><span>{note}</span></article>; }
export function Drawer({ title, open, onClose, children }: { title: string; open: boolean; onClose: () => void; children: ReactNode }) { if (!open) return null; return <div className="drawer-layer" role="dialog" aria-modal="true"><button className="drawer-backdrop" aria-label="关闭抽屉" onClick={onClose}/><aside className="drawer"><div className="drawer-heading"><div><p className="eyebrow">详情视图</p><h2>{title}</h2></div><button className="icon-button" aria-label="关闭" onClick={onClose}><X size={17}/></button></div>{children}</aside></div>; }
export function RiskLabel({ value }: { value: string }) { return <span className={`risk risk-${value.toLowerCase()}`}>{localizeStatus(value)}</span>; }
