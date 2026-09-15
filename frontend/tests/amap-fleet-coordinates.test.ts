import { describe, expect, it } from "vitest";

import { fleetNodes, fleetRoutes } from "../src/features/fleet-sandbox/fleet-sandbox-data";
import {
  closestPointOnLngLatPath,
  fleetNodeLngLat,
  fleetRouteLngLatPath,
  pointAlongLngLatPath,
  SONGMING_AMAP_BOUNDS,
} from "../src/features/fleet-sandbox/fleet-amap-coordinates";

describe("fleet AMap coordinates", () => {
  it("uses 22 named facilities in the Songming Yanglin logistics corridor", () => {
    expect(fleetNodes).toHaveLength(22);
    expect(fleetNodes.map((node) => node.name)).toEqual(expect.arrayContaining([
      "智慧物流调度中心",
      "快递集散站",
      "新能源车辆充电站",
      "应急救援站",
    ]));
  });

  it("places every dispatch node inside the Songming Yanglin map bounds", () => {
    for (const node of fleetNodes) {
      const [lng, lat] = fleetNodeLngLat(node);
      expect(lng).toBeGreaterThanOrEqual(SONGMING_AMAP_BOUNDS.west);
      expect(lng).toBeLessThanOrEqual(SONGMING_AMAP_BOUNDS.east);
      expect(lat).toBeGreaterThanOrEqual(SONGMING_AMAP_BOUNDS.south);
      expect(lat).toBeLessThanOrEqual(SONGMING_AMAP_BOUNDS.north);
    }
  });

  it("keeps route endpoints aligned with their named dispatch nodes", () => {
    const route = fleetRoutes[0];
    const path = fleetRouteLngLatPath(route);
    expect(path).toHaveLength(route.nodeIds.length);
    expect(path[0]).toEqual(fleetNodeLngLat(fleetNodes.find((node) => node.id === route.nodeIds[0])!));
    expect(path.at(-1)).toEqual(fleetNodeLngLat(fleetNodes.find((node) => node.id === route.nodeIds.at(-1))!));
  });

  it("interpolates a vehicle directly on the supplied road geometry", () => {
    const roadPath = [[103.04, 25.22], [103.05, 25.22], [103.05, 25.24]] as const;
    expect(pointAlongLngLatPath(roadPath, 0)).toEqual([103.04, 25.22]);
    expect(pointAlongLngLatPath(roadPath, 0.5)).toEqual([103.05, 25.225]);
    expect(pointAlongLngLatPath(roadPath, 1)).toEqual([103.05, 25.24]);
  });

  it("snaps a stationary vehicle to the nearest point on its road geometry", () => {
    const roadPath = [[103.04, 25.22], [103.05, 25.22], [103.05, 25.24]] as const;
    expect(closestPointOnLngLatPath(roadPath, [103.045, 25.222])).toEqual([103.045, 25.22]);
  });
  it("never emits NaN coordinates when progress or target data is invalid", () => {
    const roadPath = [[103.04, 25.22], [103.05, 25.22], [103.05, 25.24]] as const;
    expect(pointAlongLngLatPath(roadPath, Number.NaN)).toEqual(roadPath[0]);
    expect(closestPointOnLngLatPath(roadPath, [Number.NaN, Number.NaN])).toEqual(roadPath[0]);
  });
});
