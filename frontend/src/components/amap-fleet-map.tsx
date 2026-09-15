import { load } from "@amap/amap-jsapi-loader";
import { CarFront, Navigation } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { fleetNodes, fleetRoutes, fleetStatusMeta, type FleetMapNode, type FleetRoute } from "../features/fleet-sandbox/fleet-sandbox-data";
import {
  closestPointOnLngLatPath,
  fleetNodeLngLat,
  pointAlongLngLatPath,
  SONGMING_AMAP_CENTER,
  type FleetLngLat,
} from "../features/fleet-sandbox/fleet-amap-coordinates";
import {
  fleetRouteHeading,
  fleetRouteMotionProgress,
  fleetVehicleOverlapOffsets,
} from "../features/fleet-sandbox/fleet-motion-geometry";
import { fleetOperationRouteSpecs, fleetRescueUnitPresentation } from "../features/fleet-sandbox/fleet-operation-presentation";
import type { FleetPositionSnapshot } from "../features/fleet-sandbox/fleet-simulation";
import type { VehicleOperationSnapshot } from "../types/vehicle-operations";

export type AmapLoadState = "LOADING" | "READY" | "FALLBACK";

interface AmapFleetMapProps {
  apiKey: string;
  securityCode: string;
  vehicles: FleetPositionSnapshot[];
  playing: boolean;
  routeIds: string[];
  roadPlanningRouteIds?: string[];
  nodeIds: string[];
  criticalRouteIds: string[];
  selectedVehicleId: string;
  blockedEdgeIds: string[];
  mapMode: "STANDARD" | "SATELLITE";
  perspective: boolean;
  zoom: number;
  resetSequence: number;
  followVehicle: boolean;
  showLabels: boolean;
  showRoutes: boolean;
  showNodes: boolean;
  showRiskAreas: boolean;
  showTraffic: boolean;
  geofenceMode: boolean;
  onFollowChange: (following: boolean) => void;
  operationSnapshot?: VehicleOperationSnapshot | null;
  onVehicleSelect: (vehicleId: string) => void;
  onRouteSelect: (routeId: string) => void;
  onStateChange: (state: AmapLoadState) => void;
}

interface AmapOverlay {
  on?: (eventName: string, listener: () => void) => void;
  open?: (map: AmapMap, position: FleetLngLat) => void;
  close?: () => void;
  setPosition?: (position: FleetLngLat) => void;
  moveTo?: (position: FleetLngLat, options?: Record<string, unknown>) => void;
}

interface AmapMap {
  on: (eventName: string, listener: () => void) => void;
  add: (overlays: AmapOverlay | AmapOverlay[]) => void;
  remove: (overlays: AmapOverlay | AmapOverlay[]) => void;
  addControl: (control: AmapOverlay) => void;
  destroy: () => void;
  setLayers: (layers: AmapOverlay[]) => void;
  setMapStyle: (style: string) => void;
  setZoom: (zoom: number) => void;
  setPitch: (pitch: number) => void;
  setFitView: (overlays?: AmapOverlay[], immediately?: boolean, avoid?: number[]) => void;
  setCenter: (center: FleetLngLat, immediately?: boolean, duration?: number) => void;
  getCenter?: () => unknown;
}

interface DrivingResult {
  routes?: Array<{ steps?: Array<{ path?: unknown[] }> }>;
}

interface AmapDriving {
  search: (
    origin: FleetLngLat,
    destination: FleetLngLat,
    options: { waypoints?: FleetLngLat[] },
    callback: (status: string, result: DrivingResult) => void,
  ) => void;
}

type OverlayConstructor = new (options?: Record<string, unknown>) => AmapOverlay;

interface AmapApi {
  Map: new (container: HTMLElement, options: Record<string, unknown>) => AmapMap;
  Marker: OverlayConstructor;
  Polyline: OverlayConstructor;
  Circle: OverlayConstructor;
  InfoWindow: OverlayConstructor;
  Scale: OverlayConstructor;
  ToolBar: OverlayConstructor;
  Driving: new (options?: Record<string, unknown>) => AmapDriving;
  TileLayer: OverlayConstructor & {
    Satellite: OverlayConstructor;
    RoadNet: OverlayConstructor;
    Traffic: OverlayConstructor;
  };
}

interface VehicleMarkerRecord {
  marker: AmapOverlay;
  content: HTMLElement;
  presentationKey: string;
}

interface RescueMarkerRecord {
  marker: AmapOverlay;
  content: HTMLElement;
  routeId: string;
}

interface VehicleMotionSync {
  phase: number;
  synchronizedAt: number;
  routeId: string;
  status: FleetPositionSnapshot["status"];
  speedKph: number;
  nodeId: string;
}

declare global {
  interface Window {
    _AMapSecurityConfig?: { securityJsCode: string };
  }
}

const routeById = new Map(fleetRoutes.map((route) => [route.id, route]));
const nodeById = new Map(fleetNodes.map((node) => [node.id, node]));

const vehicleMarkerPresentation: Record<FleetPositionSnapshot["status"], {
  accent: string;
  glow: string;
  surface: string;
  visualState: "moving" | "dispatching" | "standby" | "fault";
}> = {
  IN_TRANSIT: { accent: "#22d3ee", glow: "rgba(34, 211, 238, .42)", surface: "rgba(5, 50, 62, .92)", visualState: "moving" },
  AVAILABLE: { accent: "#94a3b8", glow: "rgba(148, 163, 184, .28)", surface: "rgba(25, 38, 54, .9)", visualState: "standby" },
  DISPATCHING: { accent: "#8b5cf6", glow: "rgba(139, 92, 246, .46)", surface: "rgba(41, 24, 79, .92)", visualState: "dispatching" },
  BROKEN: { accent: "#ef4444", glow: "rgba(239, 68, 68, .46)", surface: "rgba(76, 22, 28, .92)", visualState: "fault" },
  MAINTENANCE: { accent: "#64748b", glow: "rgba(100, 116, 139, .26)", surface: "rgba(28, 38, 52, .9)", visualState: "standby" },
};

const vehicleIconMarkup = renderToStaticMarkup(<CarFront aria-hidden="true" strokeWidth={1.8} />);
const vehicleHeadingMarkup = renderToStaticMarkup(<Navigation aria-hidden="true" fill="currentColor" strokeWidth={1.5} />);
const vehicleLegendItems = [
  { label: "行驶中", visualState: "moving" },
  { label: "调度中", visualState: "dispatching" },
  { label: "待命", visualState: "standby" },
  { label: "故障", visualState: "fault" },
] as const;

function createVehicleMarkerContent(vehicle: FleetPositionSnapshot, selected: boolean, showLabel: boolean): HTMLElement {
  const presentation = vehicleMarkerPresentation[vehicle.status];
  const root = document.createElement("button");
  root.type = "button";
  root.className = `amap-fleet-vehicle is-${vehicle.status.toLowerCase()} ${selected ? "is-selected" : ""}`;
  root.setAttribute("aria-label", `${vehicle.id}，${fleetStatusMeta[vehicle.status].label}`);
  root.dataset.vehicleId = vehicle.id;
  root.dataset.vehicleVisualState = presentation.visualState;
  root.dataset.amapRouteId = vehicle.routeId;
  root.dataset.amapProgress = String(vehicle.progress);
  root.style.setProperty("--vehicle-color", presentation.accent);
  root.style.setProperty("--vehicle-glow", presentation.glow);
  root.style.setProperty("--vehicle-surface", presentation.surface);

  const radar = document.createElement("span");
  radar.className = "amap-fleet-vehicle__radar";
  radar.setAttribute("aria-hidden", "true");
  const directional = document.createElement("span");
  directional.className = "amap-fleet-vehicle__directional";
  directional.setAttribute("aria-hidden", "true");
  const heading = document.createElement("span");
  heading.className = "amap-fleet-vehicle__heading";
  heading.innerHTML = vehicleHeadingMarkup;
  const glyph = document.createElement("span");
  glyph.className = "amap-fleet-vehicle__glyph";
  glyph.dataset.vehicleGlyph = "truck";
  glyph.innerHTML = vehicleIconMarkup;
  directional.append(heading, glyph);
  root.append(radar, directional);

  if (showLabel && (vehicle.status === "DISPATCHING" || vehicle.status === "BROKEN")) {
    const label = document.createElement("strong");
    label.dataset.vehicleStateLabel = "true";
    label.textContent = fleetStatusMeta[vehicle.status].label;
    root.append(label);
  }
  return root;
}

function createNodeMarkerContent(node: FleetMapNode): HTMLElement {
  const root = document.createElement("div");
  const facilityClass = {
    N19: "is-dispatch-center",
    N20: "is-express-station",
    N21: "is-charging-station",
    N22: "is-rescue-station",
  }[node.id] ?? "";
  root.className = `amap-fleet-node is-${node.kind.toLowerCase()} ${facilityClass}`;
  root.dataset.amapNodeId = node.id;
  const symbol = document.createElement("i");
  const label = document.createElement("span");
  label.textContent = node.name;
  root.append(symbol, label);
  return root;
}

function createVehicleInfoContent(vehicle: FleetPositionSnapshot): HTMLElement {
  const root = document.createElement("div");
  root.className = "amap-fleet-info";
  root.dataset.vehicleVisualState = vehicleMarkerPresentation[vehicle.status].visualState;
  root.style.setProperty("--vehicle-color", vehicleMarkerPresentation[vehicle.status].accent);
  const heading = document.createElement("div");
  heading.className = "amap-fleet-info__heading";
  const statusDot = document.createElement("i");
  statusDot.setAttribute("aria-hidden", "true");
  const title = document.createElement("strong");
  title.textContent = vehicle.id;
  heading.append(statusDot, title);
  const speed = document.createElement("span");
  speed.className = "amap-fleet-info__speed";
  speed.textContent = `${vehicle.speedKph} km/h`;
  const status = document.createElement("span");
  status.className = "amap-fleet-info__status";
  status.textContent = fleetStatusMeta[vehicle.status].label;
  const route = document.createElement("span");
  route.className = "amap-fleet-info__route";
  route.textContent = vehicle.routeDisplayName;
  const location = document.createElement("small");
  location.textContent = vehicle.locationLabel;
  root.append(heading, speed, status, route, location);
  return root;
}

function createRescueMarkerContent(unitId: string, label: string): HTMLElement {
  const root = document.createElement("div");
  root.className = "amap-fleet-rescue-unit";
  root.innerHTML = "<i></i><span></span>";
  root.querySelector("i")!.textContent = "救";
  root.querySelector("span")!.textContent = `${unitId} · ${label}`;
  return root;
}

function routeColor(route: FleetRoute, critical: boolean): string {
  if (route.id === "ROUTE-10" && critical) return "#ff9f1c";
  if (route.id === "ROUTE-02" && critical) return "#22d3ee";
  return critical ? "#2f9cf4" : route.color;
}

function vehicleOperationPathId(vehicleId: string, snapshot: VehicleOperationSnapshot | null): string | null {
  if (vehicleId === snapshot?.incident.replacement_vehicle_id) return "OP-REPLACEMENT";
  if (vehicleId === snapshot?.incident.vehicle_id && snapshot.rescue.status === "LOADED") return "OP-TOW";
  return null;
}

function normalizeLngLat(value: unknown): FleetLngLat | null {
  if (Array.isArray(value) && value.length >= 2) {
    const lng = Number(value[0]);
    const lat = Number(value[1]);
    return Number.isFinite(lng) && Number.isFinite(lat) ? [lng, lat] : null;
  }
  if (!value || typeof value !== "object") return null;
  const candidate = value as { getLng?: () => unknown; getLat?: () => unknown; lng?: unknown; lat?: unknown };
  const lng = Number(candidate.getLng?.() ?? candidate.lng);
  const lat = Number(candidate.getLat?.() ?? candidate.lat);
  return Number.isFinite(lng) && Number.isFinite(lat) ? [lng, lat] : null;
}

function isFiniteLngLat(value: readonly [number, number] | null | undefined): value is FleetLngLat {
  if (!value) return false;
  return Number.isFinite(value[0]) && Number.isFinite(value[1]);
}

function drivingResultPath(result: DrivingResult): FleetLngLat[] {
  return (result.routes?.[0]?.steps ?? [])
    .flatMap((step) => step.path ?? [])
    .map(normalizeLngLat)
    .filter((point): point is FleetLngLat => Boolean(point));
}

function requestDrivingNodePath(AMap: AmapApi, nodeIds: readonly string[]): Promise<FleetLngLat[] | null> {
  const fallbackPath = nodeIds
    .map((nodeId) => nodeById.get(nodeId))
    .filter((node): node is FleetMapNode => Boolean(node))
    .map(fleetNodeLngLat);
  if (fallbackPath.length < 2) return Promise.resolve(null);
  return new Promise((resolve) => {
    try {
      const driving = new AMap.Driving({ policy: 0, extensions: "all" });
      driving.search(
        fallbackPath[0],
        fallbackPath[fallbackPath.length - 1],
        { waypoints: fallbackPath.slice(1, -1) },
        (status, result) => {
          const plannedPath = status === "complete" ? drivingResultPath(result) : [];
          resolve(plannedPath.length >= 2 ? plannedPath : null);
        },
      );
    } catch {
      resolve(null);
    }
  });
}

function requestDrivingPath(AMap: AmapApi, route: FleetRoute): Promise<FleetLngLat[] | null> {
  return requestDrivingNodePath(AMap, route.nodeIds);
}

function waitForRouteRequestGap(delayMs: number): Promise<void> {
  if (import.meta.env.MODE === "test") return Promise.resolve();
  return new Promise((resolve) => window.setTimeout(resolve, delayMs));
}

const ROAD_PATH_CACHE_KEY = "countyflow:amap-road-paths:v2";
const ROUTE_MATCH_CONCURRENCY = 2;

function routePathCacheKey(route: Pick<FleetRoute, "id" | "nodeIds">): string {
  return [route.id, ...route.nodeIds].join(":");
}

function readRoadPathCache(): Record<string, FleetLngLat[]> {
  if (typeof window === "undefined") return {};
  try {
    const parsed = JSON.parse(window.sessionStorage.getItem(ROAD_PATH_CACHE_KEY) ?? "{}") as Record<string, unknown>;
    return Object.fromEntries(Object.entries(parsed).flatMap(([key, value]) => {
      if (!Array.isArray(value)) return [];
      const path = value.map(normalizeLngLat).filter((point): point is FleetLngLat => Boolean(point));
      return path.length === value.length && path.length >= 2 ? [[key, path]] : [];
    }));
  } catch {
    return {};
  }
}

function writeRoadPathCache(cache: Record<string, FleetLngLat[]>): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(ROAD_PATH_CACHE_KEY, JSON.stringify(cache));
  } catch {
    // Route caching is an optimization; storage failures must not block the live map.
  }
}

export function AmapFleetMap({
  apiKey,
  securityCode,
  vehicles,
  playing,
  routeIds,
  roadPlanningRouteIds,
  nodeIds,
  criticalRouteIds,
  selectedVehicleId,
  blockedEdgeIds,
  mapMode,
  perspective,
  zoom,
  resetSequence,
  followVehicle,
  showLabels,
  showRoutes,
  showNodes,
  showRiskAreas,
  showTraffic,
  geofenceMode,
  onFollowChange,
  operationSnapshot = null,
  onVehicleSelect,
  onRouteSelect,
  onStateChange,
}: AmapFleetMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<AmapMap | null>(null);
  const apiRef = useRef<AmapApi | null>(null);
  const routeOverlaysRef = useRef<AmapOverlay[]>([]);
  const operationRouteOverlaysRef = useRef<AmapOverlay[]>([]);
  const nodeOverlaysRef = useRef<AmapOverlay[]>([]);
  const vehicleMarkersRef = useRef<Map<string, VehicleMarkerRecord>>(new Map());
  const vehiclesRef = useRef(vehicles);
  const vehicleMotionSyncRef = useRef<Map<string, VehicleMotionSync>>(new Map());
  const selectedInfoRef = useRef<AmapOverlay | null>(null);
  const infoOpenTimersRef = useRef<Set<number>>(new Set());
  const riskOverlaysRef = useRef<AmapOverlay[]>([]);
  const rescueMarkerRef = useRef<RescueMarkerRecord | null>(null);
  const drivingGenerationRef = useRef(0);
  const operationGenerationRef = useRef(0);
  const roadPathsRef = useRef<Record<string, FleetLngLat[]>>({});
  const roadPathCacheRef = useRef<Record<string, FleetLngLat[]> | null>(null);
  const operationPathsRef = useRef<Record<string, FleetLngLat[]>>({});
  const userHasMovedMapRef = useRef(false);
  const onStateChangeRef = useRef(onStateChange);
  const onRouteSelectRef = useRef(onRouteSelect);
  const onVehicleSelectRef = useRef(onVehicleSelect);
  const onFollowChangeRef = useRef(onFollowChange);
  const followVehicleRef = useRef(followVehicle);
  const [loadState, setLoadState] = useState<AmapLoadState>("LOADING");
  const [roadPathCount, setRoadPathCount] = useState(0);
  const [operationRoadCount, setOperationRoadCount] = useState(0);
  const [mapDragCount, setMapDragCount] = useState(0);
  const [isMapDragging, setIsMapDragging] = useState(false);
  const [mapCenter, setMapCenter] = useState(() => SONGMING_AMAP_CENTER.join(","));
  const routeKey = routeIds.join(",");
  const roadPlanningKey = (roadPlanningRouteIds?.length ? roadPlanningRouteIds : fleetRoutes.map((route) => route.id)).join(",");
  const nodeKey = nodeIds.join(",");
  const criticalRouteKey = criticalRouteIds.join(",");
  const blockedEdgeKey = blockedEdgeIds.join(",");
  const vehiclePresentationKey = vehicles
    .map((vehicle) => `${vehicle.id}:${vehicle.routeId}:${vehicle.status}`)
    .join("|");
  const visibleRoutes = useMemo(() => routeKey.split(",").filter(Boolean).map((id) => routeById.get(id)).filter((route): route is FleetRoute => Boolean(route)), [routeKey]);
  const roadPlanningRoutes = useMemo(() => roadPlanningKey.split(",").filter(Boolean).map((id) => routeById.get(id)).filter((route): route is FleetRoute => Boolean(route)), [roadPlanningKey]);
  const visibleNodes = useMemo(() => nodeKey.split(",").filter(Boolean).map((id) => nodeById.get(id)).filter((node): node is FleetMapNode => Boolean(node)), [nodeKey]);
  const criticalRoutes = useMemo(() => criticalRouteKey.split(",").filter(Boolean), [criticalRouteKey]);
  const blockedEdges = useMemo(() => blockedEdgeKey.split(",").filter(Boolean), [blockedEdgeKey]);
  const operationRoutes = useMemo(() => fleetOperationRouteSpecs(operationSnapshot), [operationSnapshot]);
  const operationRoutesRef = useRef(operationRoutes);
  const operationRouteKey = operationRoutes.map((route) => `${route.id}:${route.nodeIds.join("-")}`).join("|");
  const operationStyleKey = operationRoutes.map((route) => `${route.id}:${route.status}`).join("|");

  if (roadPathCacheRef.current === null) roadPathCacheRef.current = readRoadPathCache();

  useEffect(() => {
    operationRoutesRef.current = operationRoutes;
  }, [operationRoutes]);

  useEffect(() => {
    onStateChangeRef.current = onStateChange;
    onRouteSelectRef.current = onRouteSelect;
    onVehicleSelectRef.current = onVehicleSelect;
    onFollowChangeRef.current = onFollowChange;
  }, [onFollowChange, onRouteSelect, onStateChange, onVehicleSelect]);

  useEffect(() => {
    followVehicleRef.current = followVehicle;
  }, [followVehicle]);

  useEffect(() => {
    if (!containerRef.current) return undefined;
    const vehicleMarkers = vehicleMarkersRef.current;
    const infoOpenTimers = infoOpenTimersRef.current;
    let active = true;
    let settled = false;
    let readinessTimer: number | undefined;
    setLoadState("LOADING");
    onStateChangeRef.current("LOADING");
    window._AMapSecurityConfig = { securityJsCode: securityCode };

    void load({
      key: apiKey,
      version: "2.0",
      plugins: ["AMap.Scale", "AMap.ToolBar", "AMap.Driving"],
    }).then((loadedApi: unknown) => {
      if (!active || !containerRef.current) return;
      const AMap = loadedApi as AmapApi;
      const map = new AMap.Map(containerRef.current, {
        center: SONGMING_AMAP_CENTER,
        zoom: 11.5,
        mapStyle: "amap://styles/darkblue",
        viewMode: "3D",
        pitch: 0,
        rotation: 0,
        resizeEnable: true,
        animateEnable: true,
        terrain: false,
        dragEnable: true,
        scrollWheel: true,
        doubleClickZoom: true,
        touchZoom: true,
        touchZoomCenter: 1,
        keyboardEnable: true,
      });
      map.addControl(new AMap.Scale({ position: "LB" }));
      map.addControl(new AMap.ToolBar({ position: "RB", liteStyle: true }));
      apiRef.current = AMap;
      mapRef.current = map;
      map.on("dragstart", () => {
        userHasMovedMapRef.current = true;
        if (followVehicleRef.current) onFollowChangeRef.current(false);
        setIsMapDragging(true);
      });
      map.on("dragend", () => {
        const center = normalizeLngLat(map.getCenter?.());
        if (center) setMapCenter(center.join(","));
        setIsMapDragging(false);
        setMapDragCount((value) => value + 1);
      });
      const markReady = () => {
        if (!active || settled) return;
        settled = true;
        if (readinessTimer) window.clearTimeout(readinessTimer);
        setLoadState("READY");
        onStateChangeRef.current("READY");
      };
      map.on("complete", markReady);
      readinessTimer = window.setTimeout(() => {
        if (!active || settled) return;
        settled = true;
        setLoadState("FALLBACK");
        onStateChangeRef.current("FALLBACK");
      }, 12000);
    }).catch(() => {
      if (!active) return;
      settled = true;
      setLoadState("FALLBACK");
      onStateChangeRef.current("FALLBACK");
    });

    return () => {
      active = false;
      if (readinessTimer) window.clearTimeout(readinessTimer);
      drivingGenerationRef.current += 1;
      operationGenerationRef.current += 1;
      roadPathsRef.current = {};
      operationPathsRef.current = {};
      userHasMovedMapRef.current = false;
      for (const timerId of infoOpenTimers) window.clearTimeout(timerId);
      infoOpenTimers.clear();
      try {
        try {
          selectedInfoRef.current?.close?.();
        } catch {
          // Ignore provider errors while replacing a selected vehicle InfoWindow.
        }
      } catch {
        // AMap can throw while closing an InfoWindow during map teardown.
      }
      selectedInfoRef.current = null;
      rescueMarkerRef.current = null;
      vehicleMarkers.clear();
      try {
        mapRef.current?.destroy();
      } catch {
        // The component is already unmounting; provider teardown must not crash React.
      }
      mapRef.current = null;
      apiRef.current = null;
    };
  }, [apiKey, securityCode]);

  useEffect(() => {
    const map = mapRef.current;
    const AMap = apiRef.current;
    if (!map || !AMap || loadState !== "READY") return;
    const trafficLayer = showTraffic ? new AMap.TileLayer.Traffic({ autoRefresh: true, interval: 180 }) : null;
    if (mapMode === "SATELLITE") {
      map.setLayers([new AMap.TileLayer.Satellite(), new AMap.TileLayer.RoadNet(), trafficLayer].filter((layer): layer is AmapOverlay => Boolean(layer)));
    } else {
      map.setMapStyle("amap://styles/darkblue");
      map.setLayers([new AMap.TileLayer(), trafficLayer].filter((layer): layer is AmapOverlay => Boolean(layer)));
    }
  }, [loadState, mapMode, showTraffic]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || loadState !== "READY") return;
    map.setZoom(11.5 + (zoom - 1) * 3);
    map.setPitch(perspective ? 34 : 0);
  }, [loadState, perspective, zoom]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || loadState !== "READY" || !routeOverlaysRef.current.length) return;
    userHasMovedMapRef.current = false;
    map.setFitView(routeOverlaysRef.current, true, [76, 92, 62, 185]);
  }, [loadState, resetSequence]);

  useEffect(() => {
    const AMap = apiRef.current;
    if (!AMap || loadState !== "READY") return;
    const generation = ++drivingGenerationRef.current;
    let active = true;
    const criticalSet = new Set(criticalRoutes);
    const planningOrder = [...roadPlanningRoutes].sort((left, right) =>
      Number(criticalSet.has(right.id)) - Number(criticalSet.has(left.id)));
    const cachedPaths = roadPathCacheRef.current ?? {};
    roadPathsRef.current = planningOrder.reduce<Record<string, FleetLngLat[]>>((paths, route) => {
      const cachedPath = cachedPaths[routePathCacheKey(route)];
      if (cachedPath) paths[route.id] = cachedPath;
      return paths;
    }, { ...roadPathsRef.current });
    setRoadPathCount(planningOrder.filter((route) => Boolean(roadPathsRef.current[route.id])).length);

    const routesToPlan = planningOrder.filter((route) => !roadPathsRef.current[route.id]);
    let nextRouteIndex = 0;
    const planRoutesConcurrently = async () => {
      while (nextRouteIndex < routesToPlan.length) {
        const route = routesToPlan[nextRouteIndex];
        nextRouteIndex += 1;
        if (!active || generation !== drivingGenerationRef.current || !mapRef.current) return;
        let plannedPath: FleetLngLat[] | null = null;
        for (let attempt = 0; attempt < 3 && !plannedPath; attempt += 1) {
          plannedPath = await requestDrivingPath(AMap, route);
          if (!plannedPath && attempt < 2) await waitForRouteRequestGap(500 * (attempt + 1));
        }
        if (!active || generation !== drivingGenerationRef.current || !mapRef.current) return;
        if (plannedPath) {
          roadPathsRef.current = { ...roadPathsRef.current, [route.id]: plannedPath };
          const nextCache = { ...(roadPathCacheRef.current ?? {}), [routePathCacheKey(route)]: plannedPath };
          roadPathCacheRef.current = nextCache;
          writeRoadPathCache(nextCache);
          setRoadPathCount(planningOrder.filter((candidate) => Boolean(roadPathsRef.current[candidate.id])).length);
        }
      }
    };
    const workerCount = Math.min(ROUTE_MATCH_CONCURRENCY, routesToPlan.length);
    void Promise.all(Array.from({ length: workerCount }, () => planRoutesConcurrently()));
    return () => { active = false; };
  }, [criticalRoutes, loadState, roadPlanningRoutes]);

  useEffect(() => {
    const AMap = apiRef.current;
    if (!AMap || loadState !== "READY" || roadPathCount < roadPlanningRoutes.length) return;
    operationGenerationRef.current += 1;
    const generation = operationGenerationRef.current;
    let active = true;
    operationPathsRef.current = {};
    setOperationRoadCount(0);

    const planOperationRoutes = async () => {
      const routes = operationRoutesRef.current;
      for (const [routeIndex, route] of routes.entries()) {
        let plannedPath: FleetLngLat[] | null = null;
        for (let attempt = 0; attempt < 3 && !plannedPath; attempt += 1) {
          plannedPath = await requestDrivingNodePath(AMap, route.nodeIds);
          if (!plannedPath && attempt < 2) await waitForRouteRequestGap(500 * (attempt + 1));
        }
        if (!active || generation !== operationGenerationRef.current || !mapRef.current) return;
        if (plannedPath) {
          operationPathsRef.current = { ...operationPathsRef.current, [route.id]: plannedPath };
          setOperationRoadCount(Object.keys(operationPathsRef.current).length);
        }
        if (routeIndex < routes.length - 1) await waitForRouteRequestGap(180);
      }
    };
    void planOperationRoutes();
    return () => { active = false; };
  }, [loadState, operationRouteKey, roadPathCount, roadPlanningRoutes.length]);

  useEffect(() => {
    const map = mapRef.current;
    const AMap = apiRef.current;
    if (!map || !AMap || loadState !== "READY") return;
    map.remove(routeOverlaysRef.current);
    routeOverlaysRef.current = [];
    if (!showRoutes) return;

    const criticalSet = new Set(criticalRoutes);
    routeOverlaysRef.current = visibleRoutes.flatMap((route) => {
      const plannedPath = roadPathsRef.current[route.id];
      if (!plannedPath) return [];
      const critical = criticalSet.has(route.id);
      const overlay = new AMap.Polyline({
        path: plannedPath,
        strokeColor: routeColor(route, critical),
        strokeOpacity: critical ? 0.94 : 0.22,
        strokeWeight: critical ? 7 : 3,
        strokeStyle: route.id === "ROUTE-10" && critical ? "dashed" : "solid",
        lineJoin: "round",
        lineCap: "round",
        borderWeight: critical ? 2 : 0,
        outlineColor: "rgba(255,255,255,.9)",
        zIndex: critical ? 45 : 20,
        showDir: critical,
        bubble: true,
      });
      overlay.on?.("click", () => onRouteSelectRef.current(route.id));
      return [overlay];
    });
    if (routeOverlaysRef.current.length) {
      map.add(routeOverlaysRef.current);
      const allVisibleRoutesPlanned = routeOverlaysRef.current.length === visibleRoutes.length;
      if (allVisibleRoutesPlanned && !userHasMovedMapRef.current) {
        map.setFitView(routeOverlaysRef.current, true, [76, 92, 62, 185]);
      }
    }
  }, [criticalRoutes, loadState, roadPathCount, showRoutes, visibleRoutes]);

  useEffect(() => {
    const map = mapRef.current;
    const AMap = apiRef.current;
    if (!map || !AMap || loadState !== "READY") return;
    map.remove(operationRouteOverlaysRef.current);
    operationRouteOverlaysRef.current = [];
    if (!showRoutes) return;
    operationRouteOverlaysRef.current = operationRoutesRef.current.flatMap((route) => {
      const path = operationPathsRef.current[route.id];
      if (!path) return [];
      return [new AMap.Polyline({
        path,
        strokeColor: route.color,
        strokeOpacity: 0.96,
        strokeWeight: route.kind === "TOW" ? 7 : 6,
        strokeStyle: route.kind === "TOW" ? "dashed" : "solid",
        lineJoin: "round",
        lineCap: "round",
        borderWeight: 2,
        outlineColor: "rgba(255,255,255,.92)",
        zIndex: 58,
        showDir: true,
        bubble: true,
      })];
    });
    if (operationRouteOverlaysRef.current.length) map.add(operationRouteOverlaysRef.current);
  }, [loadState, operationRoadCount, operationRouteKey, operationStyleKey, showRoutes]);

  useEffect(() => {
    const map = mapRef.current;
    const AMap = apiRef.current;
    const presentation = fleetRescueUnitPresentation(operationSnapshot);
    if (!map || !AMap || loadState !== "READY") return;
    if (!presentation) {
      if (rescueMarkerRef.current) map.remove(rescueMarkerRef.current.marker);
      rescueMarkerRef.current = null;
      return;
    }
    const path = operationPathsRef.current[presentation.routeId];
    if (!path) return;
    const position = pointAlongLngLatPath(path, presentation.progress);
    if (!isFiniteLngLat(position)) return;
    const existing = rescueMarkerRef.current;
    if (!existing) {
      const content = createRescueMarkerContent(presentation.unitId, presentation.label);
      content.dataset.operationRouteId = presentation.routeId;
      content.dataset.operationProgress = String(presentation.progress);
      const marker = new AMap.Marker({ position, content, anchor: "center", zIndex: 110, bubble: true });
      map.add(marker);
      rescueMarkerRef.current = { marker, content, routeId: presentation.routeId };
      return;
    }
    existing.content.querySelector("span")!.textContent = `${presentation.unitId} · ${presentation.label}`;
    existing.content.dataset.operationRouteId = presentation.routeId;
    existing.content.dataset.operationProgress = String(presentation.progress);
    existing.marker.moveTo?.(position, { duration: 900, autoRotation: true });
    if (!existing.marker.moveTo) existing.marker.setPosition?.(position);
    existing.routeId = presentation.routeId;
  }, [loadState, operationRoadCount, operationSnapshot]);

  useEffect(() => {
    const synchronizedAt = performance.now();
    vehiclesRef.current = vehicles;
    const activeIds = new Set(vehicles.map((vehicle) => vehicle.id));
    for (const vehicleId of vehicleMotionSyncRef.current.keys()) {
      if (!activeIds.has(vehicleId)) vehicleMotionSyncRef.current.delete(vehicleId);
    }
    for (const vehicle of vehicles) {
      vehicleMotionSyncRef.current.set(vehicle.id, {
        phase: vehicle.routePhase ?? vehicle.routeProgress ?? vehicle.progress / 100,
        synchronizedAt,
        routeId: vehicle.routeId,
        status: vehicle.status,
        speedKph: vehicle.speedKph,
        nodeId: vehicle.nodeId,
      });
    }
  }, [vehicles]);

  useEffect(() => {
    const map = mapRef.current;
    const AMap = apiRef.current;
    if (!map || !AMap || loadState !== "READY") return;
    map.remove(nodeOverlaysRef.current);
    nodeOverlaysRef.current = [];
    if (!showNodes) return;
    nodeOverlaysRef.current = visibleNodes.map((node) => new AMap.Marker({
      position: fleetNodeLngLat(node),
      content: createNodeMarkerContent(node),
      anchor: "center",
      offset: [0, 0],
      zIndex: node.kind === "HUB" || node.kind === "STATION" ? 62 : 35,
      bubble: true,
    }));
    map.add(nodeOverlaysRef.current);
  }, [loadState, showNodes, visibleNodes]);

  useEffect(() => {
    const map = mapRef.current;
    const AMap = apiRef.current;
    if (!map || !AMap || loadState !== "READY") return;
    const vehiclesToRender = vehiclesRef.current;
    const overlapOffsets = fleetVehicleOverlapOffsets(vehiclesToRender.map((vehicle) => ({
      id: vehicle.id,
      routeId: vehicle.routeId,
      progress: vehicle.routeProgress ?? vehicle.progress / 100,
      moving: vehicle.status === "IN_TRANSIT" || vehicle.status === "DISPATCHING",
      nodeId: vehicle.nodeId,
    })));
    const visibleIds = new Set(vehiclesToRender.map((vehicle) => vehicle.id));
    for (const [vehicleId, record] of vehicleMarkersRef.current) {
      if (visibleIds.has(vehicleId)) continue;
      map.remove(record.marker);
      vehicleMarkersRef.current.delete(vehicleId);
    }

    for (const vehicle of vehiclesToRender) {
      const selected = vehicle.id === selectedVehicleId;
      const priority = selected || vehicle.status === "BROKEN" || vehicle.status === "DISPATCHING";
      const route = routeById.get(vehicle.routeId) ?? fleetRoutes[0];
      const operationPathId = vehicleOperationPathId(vehicle.id, operationSnapshot);
      const path = operationPathId ? operationPathsRef.current[operationPathId] : roadPathsRef.current[route.id];
      const existing = vehicleMarkersRef.current.get(vehicle.id);
      if (!path) {
        if (existing) {
          map.remove(existing.marker);
          vehicleMarkersRef.current.delete(vehicle.id);
        }
        continue;
      }
      const presentationKey = `${operationPathId ?? vehicle.routeId}:${vehicle.status}:${selected}:${showLabels && priority}`;
      if (existing?.presentationKey === presentationKey) continue;
      if (existing) map.remove(existing.marker);
      const node = nodeById.get(vehicle.nodeId);
      const isTow = operationPathId === "OP-TOW";
      const isMoving = vehicle.status === "IN_TRANSIT" || vehicle.status === "DISPATCHING" || isTow;
      const operationProgress = isTow ? fleetRescueUnitPresentation(operationSnapshot)?.progress : null;
      const position = isMoving || !node
        ? pointAlongLngLatPath(path, operationProgress ?? vehicle.routeProgress ?? vehicle.progress / 100)
        : closestPointOnLngLatPath(path, fleetNodeLngLat(node));
      const content = createVehicleMarkerContent(vehicle, selected, showLabels && priority);
      if (!isFiniteLngLat(position)) continue;
      const offset = overlapOffsets.get(vehicle.id) ?? { x: 0, y: 0 };
      const phase = vehicle.routePhase ?? vehicle.routeProgress ?? vehicle.progress / 100;
      const heading = fleetRouteHeading(path, vehicle.routeProgress ?? vehicle.progress / 100, phase);
      content.dataset.amapLng = String(position[0]);
      content.dataset.amapLat = String(position[1]);
      content.dataset.amapHeading = String(Math.round(heading));
      content.dataset.amapOverlapOffset = `${offset.x},${offset.y}`;
      content.style.setProperty("--vehicle-offset-x", `${offset.x}px`);
      content.style.setProperty("--vehicle-offset-y", `${offset.y}px`);
      content.style.setProperty("--vehicle-heading", `${heading}deg`);
      const marker = new AMap.Marker({
        position,
        content,
        anchor: "center",
        zIndex: priority ? 92 : 70,
        bubble: true,
      });
      marker.on?.("click", () => onVehicleSelectRef.current(vehicle.id));
      map.add(marker);
      vehicleMarkersRef.current.set(vehicle.id, { marker, content, presentationKey });
      if (selected) {
        try {
          selectedInfoRef.current?.close?.();
        } catch {
          // Ignore provider errors while replacing a selected vehicle InfoWindow.
        }
        const info = new AMap.InfoWindow({
          content: createVehicleInfoContent(vehicle),
          anchor: "bottom-center",
          offset: [0, -24],
          isCustom: true,
          closeWhenClickMap: true,
        });
        selectedInfoRef.current = info;
        const timerId = window.setTimeout(() => {
          infoOpenTimersRef.current.delete(timerId);
          if (mapRef.current !== map || apiRef.current !== AMap || !isFiniteLngLat(position)) return;
          try {
            info.open?.(map, position);
          } catch {
            // A stale provider instance must not surface as an application error.
          }
        }, 0);
        infoOpenTimersRef.current.add(timerId);
      }
    }
  }, [loadState, operationRoadCount, operationSnapshot, roadPathCount, selectedVehicleId, showLabels, vehiclePresentationKey]);

  useEffect(() => {
    if (loadState !== "READY" || !roadPathCount) return undefined;
    let animationFrameId = 0;
    let lastFrameAt = 0;
    let lastFollowAt = 0;
    const animateVehicles = (frameTime: number) => {
      if (frameTime - lastFrameAt >= 32) {
        lastFrameAt = frameTime;
        for (const vehicle of vehiclesRef.current) {
          const record = vehicleMarkersRef.current.get(vehicle.id);
          const sync = vehicleMotionSyncRef.current.get(vehicle.id);
          const operationPathId = vehicleOperationPathId(vehicle.id, operationSnapshot);
          const path = operationPathId ? operationPathsRef.current[operationPathId] : roadPathsRef.current[vehicle.routeId];
          if (!record || !sync || !path) continue;
          const isTow = operationPathId === "OP-TOW";
          const moving = playing && (sync.status === "IN_TRANSIT" || sync.status === "DISPATCHING" || isTow);
          const elapsedTicks = Math.max(0, frameTime - sync.synchronizedAt) / 1500;
          const phase = moving
            ? sync.phase + elapsedTicks * 0.006 * Math.max(sync.speedKph, 30) / 40
            : sync.phase;
          const towProgress = isTow ? fleetRescueUnitPresentation(operationSnapshot, Date.now())?.progress : null;
          const progress = towProgress ?? fleetRouteMotionProgress(phase);
          const node = nodeById.get(sync.nodeId);
          const position = moving || !node
            ? pointAlongLngLatPath(path, progress)
            : closestPointOnLngLatPath(path, fleetNodeLngLat(node));
          if (!isFiniteLngLat(position)) continue;
          record.marker.setPosition?.(position);
          record.content.dataset.amapLng = String(position[0]);
          record.content.dataset.amapLat = String(position[1]);
          const heading = fleetRouteHeading(path, progress, phase);
          record.content.dataset.amapHeading = String(Math.round(heading));
          record.content.style.setProperty("--vehicle-heading", `${heading}deg`);
          if (vehicle.id === selectedVehicleId) selectedInfoRef.current?.setPosition?.(position);
          if (vehicle.id === selectedVehicleId && followVehicleRef.current && frameTime - lastFollowAt >= 96) {
            mapRef.current?.setCenter(position, false, 120);
            lastFollowAt = frameTime;
          }
        }
      }
      animationFrameId = window.requestAnimationFrame(animateVehicles);
    };
    animationFrameId = window.requestAnimationFrame(animateVehicles);
    return () => window.cancelAnimationFrame(animationFrameId);
  }, [loadState, operationRoadCount, operationSnapshot, playing, roadPathCount, selectedVehicleId]);

  useEffect(() => {
    const map = mapRef.current;
    const AMap = apiRef.current;
    if (!map || !AMap || loadState !== "READY") return;
    map.remove(riskOverlaysRef.current);
    riskOverlaysRef.current = [];
    if (!showRiskAreas || (!blockedEdges.length && !geofenceMode)) return;
    const centers = geofenceMode
      ? [fleetNodeLngLat(nodeById.get("N19")!), fleetNodeLngLat(nodeById.get("N20")!)]
      : [fleetNodeLngLat(nodeById.get("N04")!)];
    riskOverlaysRef.current = centers.map((center, index) => new AMap.Circle({
        center,
        radius: geofenceMode ? 6500 + index * 1200 : 4200,
        strokeColor: geofenceMode ? "#2f9cf4" : "#ef4444",
        strokeOpacity: 0.9,
        strokeWeight: 2,
        strokeStyle: "dashed",
        fillColor: geofenceMode ? "#2f9cf4" : "#ef4444",
        fillOpacity: 0.12,
        zIndex: 18,
        bubble: true,
      }));
    map.add(riskOverlaysRef.current);
  }, [blockedEdges, geofenceMode, loadState, showRiskAreas]);

  return <div
    className={`fleet-amap-stage is-${loadState.toLowerCase()} ${isMapDragging ? "is-dragging" : ""}`}
    data-amap-state={loadState}
    data-amap-theme={mapMode === "STANDARD" ? "night" : "night-satellite"}
    data-map-drag-count={mapDragCount}
    data-map-center={mapCenter}
    data-vehicle-animation="CONTINUOUS"
    data-follow-vehicle={followVehicle}
    data-road-route-count={roadPathCount}
    data-road-planned-count={roadPathCount}
    data-operation-road-count={operationRoadCount}
  >
    <div ref={containerRef} className="fleet-amap-canvas" aria-label="高德地图县域车辆实时调度图"/>
    {loadState === "LOADING" ? <div className="fleet-amap-loading" role="status"><i/>正在加载高德实时地图</div> : null}
    {loadState === "READY" && roadPathCount < roadPlanningRoutes.length
      ? <div className="fleet-amap-routing" role="status"><i/>真实道路匹配 {roadPathCount}/{roadPlanningRoutes.length}</div>
      : null}
    {loadState === "READY" ? <div className="amap-fleet-vehicle-legend" role="group" aria-label="车辆状态图例">
      {vehicleLegendItems.map((item) => <div key={item.visualState} className={`is-${item.visualState}`}>
        <CarFront aria-hidden="true" strokeWidth={1.8}/><span>{item.label}</span>
      </div>)}
    </div> : null}
    {loadState === "FALLBACK" ? <div className="fleet-amap-fallback" role="status">高德地图暂不可用，已切换本地卫星地图</div> : null}
  </div>;
}
