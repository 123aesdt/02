import { MapPin, Warehouse } from "lucide-react";

export function RouteVisual({ compact = false }: { compact?: boolean }) {
  return (
    <div className={`route-visual ${compact ? "route-visual-compact" : ""}`} aria-label="AI route decision visualization">
      <svg viewBox="0 0 650 270" role="img" aria-label="配送中心到三个候选路线的决策图">
        <defs><linearGradient id="routeTeal" x1="0" x2="1"><stop stopColor="#35c6b0"/><stop offset="1" stopColor="#67e1ca"/></linearGradient></defs>
        <path className="road-soft" d="M65 154 C155 120 180 79 286 76 S451 46 575 69" />
        <path className="road-soft" d="M60 154 C150 178 190 228 294 202 S458 180 590 196" />
        <path className="route-line route-danger" d="M72 153 C146 151 171 103 264 108 S430 98 573 69" />
        <path className="route-line route-teal" d="M72 153 C170 178 207 220 294 202 S466 185 590 196" />
        <path className="route-line route-muted" d="M72 153 C176 155 271 154 362 142 S478 110 576 96" />
        <circle className="map-node node-origin" cx="72" cy="153" r="12"/><circle className="map-node node-danger" cx="315" cy="107" r="10"/>
        <circle className="map-node node-teal" cx="294" cy="202" r="10"/><circle className="map-node node-muted" cx="362" cy="142" r="8"/>
        <circle className="map-node node-destination" cx="590" cy="196" r="12"/>
      </svg>
      <div className="route-origin"><Warehouse size={15}/><span>中心仓</span></div>
      <div className="route-label route-label-danger"><span>新平路</span><small>高风险 · 原路线</small></div>
      <div className="route-label route-label-teal"><span>102国道</span><small>AI 推荐 · 更安全</small></div>
      <div className="route-label route-label-muted"><span>308县道</span><small>备用路线</small></div>
      <div className="route-destination"><MapPin size={16}/><span>城东站</span></div>
    </div>
  );
}
