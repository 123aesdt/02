import { load } from "@amap/amap-jsapi-loader";
import { CheckCircle2, Clock3, MapPin, Navigation, Route as RouteIcon, ShieldCheck } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { runtimeConfig } from "../config/runtime";
import type { GeoPointResponse, PublicationResultResponse, RoutePlanResponse } from "../services/api/dispatch-adapter";
import { RouteVisual } from "./route-visual";

type LngLat = [number, number];
type PublishedRouteState = "LOADING" | "READY" | "FALLBACK";

type AmapOverlay = object;

interface AmapMap {
  add: (overlays: AmapOverlay | AmapOverlay[]) => void;
  setFitView: (overlays?: AmapOverlay[], immediately?: boolean, avoid?: number[]) => void;
  destroy: () => void;
}

interface AmapDrivingResult {
  routes?: Array<{ steps?: Array<{ path?: unknown[] }> }>;
}

interface AmapDriving {
  search: (
    origin: LngLat,
    destination: LngLat,
    options: { waypoints: LngLat[] },
    callback: (status: string, result: AmapDrivingResult) => void,
  ) => void;
}

type OverlayConstructor = new (options?: Record<string, unknown>) => AmapOverlay;

interface AmapApi {
  Map: new (container: HTMLElement, options: Record<string, unknown>) => AmapMap;
  Marker: OverlayConstructor;
  Polyline: OverlayConstructor;
  Driving: new (options?: Record<string, unknown>) => AmapDriving;
}

declare global {
  interface Window {
    _AMapSecurityConfig?: { securityJsCode: string };
  }
}

function pointToLngLat(point: GeoPointResponse): LngLat | null {
  const longitude = Number(point.longitude);
  const latitude = Number(point.latitude);
  return Number.isFinite(longitude) && Number.isFinite(latitude) ? [longitude, latitude] : null;
}

function normalizeLngLat(value: unknown): LngLat | null {
  if (Array.isArray(value) && value.length >= 2) {
    const longitude = Number(value[0]);
    const latitude = Number(value[1]);
    return Number.isFinite(longitude) && Number.isFinite(latitude) ? [longitude, latitude] : null;
  }
  if (!value || typeof value !== "object") return null;
  const candidate = value as { getLng?: () => unknown; getLat?: () => unknown; lng?: unknown; lat?: unknown };
  const longitude = Number(candidate.getLng?.() ?? candidate.lng);
  const latitude = Number(candidate.getLat?.() ?? candidate.lat);
  return Number.isFinite(longitude) && Number.isFinite(latitude) ? [longitude, latitude] : null;
}

function drivingPath(result: AmapDrivingResult): LngLat[] {
  return (result.routes?.[0]?.steps ?? [])
    .flatMap((step) => step.path ?? [])
    .map(normalizeLngLat)
    .filter((point): point is LngLat => point !== null);
}

function publishedAt(value: string | null): string {
  if (!value) return "刚刚发布";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

export function PublishedAmapRouteMap({ routePlan, publication }: {
  routePlan: RoutePlanResponse;
  publication: PublicationResultResponse;
}) {
  const mapContainerRef = useRef<HTMLDivElement | null>(null);
  const realRoadRoute = routePlan.real_road_route ?? null;
  const amapEnabled = Boolean(runtimeConfig.amap?.enabled && realRoadRoute);
  const [state, setState] = useState<PublishedRouteState>(amapEnabled ? "LOADING" : "FALLBACK");
  const [matchedByClient, setMatchedByClient] = useState(false);
  const waypoints = useMemo(
    () => (realRoadRoute?.waypoints ?? []).map(pointToLngLat).filter((point): point is LngLat => point !== null),
    [realRoadRoute],
  );
  const verifiedPath = useMemo(
    () => (realRoadRoute?.polyline ?? []).map(pointToLngLat).filter((point): point is LngLat => point !== null),
    [realRoadRoute],
  );

  useEffect(() => {
    if (!amapEnabled || !realRoadRoute || !mapContainerRef.current || waypoints.length < 2) {
      setState("FALLBACK");
      return undefined;
    }

    let disposed = false;
    let map: AmapMap | null = null;
    setState("LOADING");
    setMatchedByClient(false);
    window._AMapSecurityConfig = { securityJsCode: runtimeConfig.amap.securityCode };

    const drawRoute = (AMap: AmapApi, path: LngLat[]) => {
      if (disposed || !map || path.length < 2) return false;
      const routeLine = new AMap.Polyline({
        path,
        strokeColor: "#31dfbd",
        strokeWeight: 9,
        strokeOpacity: 0.96,
        borderWeight: 2,
        outlineColor: "#071b26",
        showDir: true,
        lineJoin: "round",
        lineCap: "round",
        zIndex: 80,
      });
      const startMarker = new AMap.Marker({ position: path[0], title: "调度路线起点", label: { content: "起点", direction: "top" } });
      const endMarker = new AMap.Marker({ position: path.at(-1), title: "调度路线终点", label: { content: "终点", direction: "top" } });
      const overlays = [routeLine, startMarker, endMarker];
      map.add(overlays);
      map.setFitView(overlays, false, [72, 72, 72, 72]);
      setState("READY");
      return true;
    };

    void load({
      key: runtimeConfig.amap.key,
      version: "2.0",
      plugins: ["AMap.Driving"],
    }).then((loaded) => {
      if (disposed || !mapContainerRef.current) return;
      const AMap = loaded as unknown as AmapApi;
      map = new AMap.Map(mapContainerRef.current, {
        mapStyle: "amap://styles/darkblue",
        zoom: 12,
        center: waypoints[0],
        viewMode: "2D",
        resizeEnable: true,
        dragEnable: true,
        scrollWheel: true,
      });
      if (realRoadRoute.status === "VERIFIED" && drawRoute(AMap, verifiedPath)) return;

      const driving = new AMap.Driving({ policy: 0, extensions: "all" });
      driving.search(
        waypoints[0],
        waypoints.at(-1)!,
        { waypoints: waypoints.slice(1, -1) },
        (status, result) => {
          if (disposed) return;
          const path = status === "complete" ? drivingPath(result) : [];
          if (drawRoute(AMap, path)) setMatchedByClient(true);
          else setState("FALLBACK");
        },
      );
    }).catch(() => {
      if (!disposed) setState("FALLBACK");
    });

    return () => {
      disposed = true;
      map?.destroy();
    };
  }, [amapEnabled, realRoadRoute, verifiedPath, waypoints]);

  const distanceKm = realRoadRoute?.distance_meters !== null && realRoadRoute?.distance_meters !== undefined
    ? (realRoadRoute.distance_meters / 1000).toFixed(2)
    : routePlan.recommended_path?.distance_km ?? "—";
  const durationMinutes = realRoadRoute?.duration_seconds !== null && realRoadRoute?.duration_seconds !== undefined
    ? Math.ceil(realRoadRoute.duration_seconds / 60)
    : routePlan.recommended_path?.estimated_minutes ?? null;
  const sourceLabel = state === "FALLBACK"
    ? "本地路线可继续使用"
    : matchedByClient
      ? "高德道路已匹配"
      : state === "READY"
        ? "高德真实道路"
        : "正在匹配高德道路";

  return <section className="published-route-map" aria-labelledby="published-route-map-title" data-published-route-state={state}>
    <header className="published-route-map__heading">
      <div>
        <p className="eyebrow">司机执行路线 · 已发布</p>
        <h2 id="published-route-map-title">{publication.route_id ?? "本次调度路线"}</h2>
        <p>{publication.recipient_display_name ?? "当前司机"}，请按下方路线行驶。</p>
      </div>
      <span className={`published-route-source is-${state.toLowerCase()}`}><Navigation size={15}/>{sourceLabel}</span>
    </header>
    <div className="published-route-facts">
      <span><RouteIcon size={15}/><small>预计里程</small><strong>{distanceKm} 公里</strong></span>
      <span><Clock3 size={15}/><small>预计用时</small><strong>{durationMinutes === null ? "—" : `${durationMinutes} 分钟`}</strong></span>
      <span><ShieldCheck size={15}/><small>道路校验</small><strong>{realRoadRoute?.status === "VERIFIED" ? "服务端已验证" : "司机端实时匹配"}</strong></span>
      <span><CheckCircle2 size={15}/><small>发布时间</small><strong>{publishedAt(publication.published_at)}</strong></span>
    </div>
    <div className="published-route-map__canvas">
      <div ref={mapContainerRef} className="published-route-amap" aria-label="高德地图调度路线"/>
      {state === "LOADING" ? <div className="published-route-map__loading"><Navigation size={22}/><strong>正在匹配真实道路</strong><span>路线发布成功，正在加载高德底图…</span></div> : null}
      {state === "FALLBACK" ? <div className="published-route-fallback" data-published-route-fallback><RouteVisual routePlan={routePlan} compact/><strong>本地路线可继续使用</strong><span>高德底图暂不可用，已保留调度节点与避让路线。</span></div> : null}
      <div className="published-route-map__badge"><MapPin size={13}/>{realRoadRoute?.coordinate_system ?? "GCJ02"} · {realRoadRoute?.mapping_version ?? "本地路线"}</div>
    </div>
    <div className="published-route-instruction">
      <Navigation size={18}/>
      <div><small>调度行驶说明</small><strong>{publication.route_instruction ?? "请按地图路线安全行驶，并留意现场道路状况。"}</strong></div>
    </div>
  </section>;
}
