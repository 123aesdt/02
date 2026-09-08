"""通过 CountyFlow 公开 API 验收离线车辆接替与堵塞绕行。"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any

import httpx


def _expect(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        raise AssertionError(f"{label}：期望 {expected!r}，实际 {actual!r}")


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"{label} 应为对象")
    return value


def _list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise TypeError(f"{label} 应为数组")
    return value


def _exact_unique_map(
    values: Any,
    *,
    id_key: str,
    expected_ids: set[str],
    label: str,
) -> dict[str, dict[str, Any]]:
    items = _list(values, label)
    mapped: dict[str, dict[str, Any]] = {}
    duplicates: list[str] = []
    for index, value in enumerate(items):
        item = _object(value, f"{label}[{index}]")
        item_id = item.get(id_key)
        if not isinstance(item_id, str) or not item_id:
            raise AssertionError(f"{label}[{index}].{id_key} 应为非空字符串")
        if item_id in mapped:
            duplicates.append(item_id)
        mapped[item_id] = item
    if duplicates:
        raise AssertionError(f"{label} 存在重复 {id_key}：{sorted(set(duplicates))}")
    _expect(set(mapped), expected_ids, f"{label} ID 集合")
    return mapped


def _verify_path_topology(
    path: dict[str, Any],
    *,
    expected_nodes: list[str],
    expected_edges: list[str],
    edges_by_id: dict[str, dict[str, Any]],
    label: str,
) -> None:
    node_ids = _list(path.get("node_ids"), f"{label}节点序列")
    edge_ids = _list(path.get("edge_ids"), f"{label}道路序列")
    _expect(node_ids, expected_nodes, f"{label}节点序列")
    _expect(edge_ids, expected_edges, f"{label}道路序列")
    _expect(len(node_ids), len(edge_ids) + 1, f"{label}节点/道路数量关系")
    for index, edge_id in enumerate(edge_ids):
        edge = edges_by_id[edge_id]
        endpoints = {edge.get("from_node_id"), edge.get("to_node_id")}
        if endpoints != {node_ids[index], node_ids[index + 1]}:
            raise AssertionError(
                f"{label}拓扑不连续：{edge_id} 不能连接 "
                f"{node_ids[index]} -> {node_ids[index + 1]}"
            )


async def _json(response: httpx.Response, label: str, expected_status: int = 200) -> dict[str, Any]:
    if response.status_code != expected_status:
        raise AssertionError(f"{label} 返回 HTTP {response.status_code}：{response.text[:300]}")
    return _object(response.json(), label)


async def _resolve_order(client: httpx.AsyncClient, order_no: str) -> dict[str, Any]:
    payload = await _json(
        await client.get("/api/v1/orders", params={"query": order_no, "limit": 100}),
        f"查询运单 {order_no}",
    )
    matches = [item for item in _list(payload.get("items"), "运单列表") if item.get("order_no") == order_no]
    if len(matches) != 1:
        raise AssertionError(f"公开订单接口应唯一解析 {order_no}，实际 {len(matches)} 条")
    return _object(matches[0], order_no)


async def _submit_and_wait(
    client: httpx.AsyncClient,
    *,
    order: dict[str, Any],
    anomaly_type: str,
    description: str,
    vehicle_status: str,
    idempotency_key: str,
    timeout_seconds: float,
) -> tuple[str, dict[str, Any]]:
    created = await _json(
        await client.post(
            "/api/v1/dispatch-tasks",
            json={
                "order_id": order["row_id"],
                "driver_id": order["driver_id"],
                "vehicle_id": order["vehicle_id"],
                "vehicle_status": vehicle_status,
                "route_id": order["route_id"],
                "anomaly_type": anomaly_type,
                "anomaly_description": description,
                "idempotency_key": idempotency_key,
            },
        ),
        f"提交 {order['order_no']}",
        202,
    )
    task_id = str(created.get("task_id", ""))
    if not task_id:
        raise AssertionError("提交响应缺少 task_id")
    deadline = time.monotonic() + timeout_seconds
    last_status: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last_status = await _json(
            await client.get(f"/api/v1/dispatch-tasks/{task_id}"),
            f"查询任务 {task_id}",
        )
        if last_status.get("ready") is True:
            return task_id, await _json(
                await client.get(f"/api/v1/dispatch-tasks/{task_id}/result"),
                f"读取结果 {task_id}",
            )
        await asyncio.sleep(0.25)
    raise AssertionError(f"任务 {task_id} 未在 {timeout_seconds:.0f} 秒内完成，最后状态 {last_status.get('status')}")


def _verify_breakdown(result: dict[str, Any]) -> dict[str, Any]:
    allocation = _object(result.get("vehicle_allocation"), "车辆调度证据")
    _expect(allocation.get("original_vehicle_id"), "V-001", "原故障车辆")
    _expect(allocation.get("target_vehicle_id"), "V-005", "接替车辆")
    _expect(allocation.get("target_driver_id"), "D-003", "接替司机")
    pickup = _object(allocation.get("pickup_route"), "接驳路线")
    _expect(pickup.get("objective"), "FASTEST", "接驳目标")
    _expect(pickup.get("node_ids"), ["N15", "N04"], "接驳节点")
    _expect(pickup.get("edge_ids"), ["E20"], "接驳道路")
    _expect(pickup.get("distance_km"), "2.80", "接驳距离")
    _expect(pickup.get("estimated_minutes"), 6, "接驳耗时")
    by_id = _exact_unique_map(
        allocation.get("candidate_vehicles"),
        id_key="vehicle_id",
        expected_ids={f"V-{index:03d}" for index in range(1, 13)},
        label="候选车辆",
    )
    candidates = list(by_id.values())
    selected = [item for item in candidates if item.get("vehicle_id") == allocation.get("target_vehicle_id")]
    _expect(len(selected), 1, "入选车辆在候选集合中的唯一性")
    selected_candidate = by_id["V-005"]
    _expect(selected_candidate.get("driver_id"), "D-003", "V-005 候选司机")
    _expect(selected_candidate.get("eligible"), True, "V-005 合格状态")
    _expect(selected_candidate.get("score"), "93.4", "V-005 总分")
    _expect(selected_candidate.get("scoring_formula"), "FLEET_SCORE_V1", "V-005 评分公式")
    _expect(selected_candidate.get("pickup_distance_km"), "2.80", "V-005 接驳距离")
    _expect(selected_candidate.get("pickup_eta_minutes"), 6, "V-005 接驳耗时")
    selected_pickup = _object(selected_candidate.get("pickup_route"), "V-005 接驳路线")
    for field in (
        "objective",
        "node_ids",
        "edge_ids",
        "distance_km",
        "estimated_minutes",
        "risk_cost",
        "visited_node_count",
        "scoring_formula",
    ):
        _expect(selected_pickup.get(field), pickup.get(field), f"V-005 接驳路线 {field}")
    _expect(selected_candidate.get("exclusion_reasons"), [], "V-005 排除原因")
    v001_reasons = set(_list(by_id["V-001"].get("exclusion_reasons"), "V-001 排除原因"))
    if not {"ORIGINAL_VEHICLE_EXCLUDED", "VEHICLE_UNAVAILABLE"}.issubset(v001_reasons):
        raise AssertionError("V-001 缺少原故障车辆排除解释")
    for vehicle_id, item in by_id.items():
        eligible = item.get("eligible")
        if not isinstance(eligible, bool):
            raise TypeError(f"{vehicle_id}.eligible 应为布尔值")
        reasons = _list(item.get("exclusion_reasons"), f"{vehicle_id} 排除原因")
        if eligible:
            _expect(reasons, [], f"{vehicle_id} 合格候选不得有排除原因")
            for field in ("driver_id", "pickup_route", "pickup_distance_km", "pickup_eta_minutes", "score"):
                if item.get(field) is None:
                    raise AssertionError(f"{vehicle_id} 合格候选缺少 {field}")
        elif not reasons:
            raise AssertionError(f"{vehicle_id} 不合格候选缺少排除原因")
    return {"task_id": result["task_id"], "candidate_count": len(candidates), "selected_score": "93.4"}


def _verify_blocked(result: dict[str, Any]) -> dict[str, Any]:
    route = _object(result.get("route_plan"), "路线重算证据")
    original = _object(route.get("original_path"), "原路线")
    recommended = _object(route.get("recommended_path"), "新路线")

    if "E04" in _list(recommended.get("edge_ids"), "新道路序列"):
        raise AssertionError("新路线仍包含堵塞边 E04")
    _expect(route.get("blocked_edge_ids"), ["E04"], "堵塞边")
    _expect(route.get("distance_delta_km"), "3.20", "里程增量")
    _expect(route.get("eta_delta_minutes"), 4, "耗时增量")
    _expect(route.get("algorithm"), "DIJKSTRA_V1", "路径算法")
    network_version = route.get("road_network_version")
    if not isinstance(network_version, int) or isinstance(network_version, bool) or network_version < 1:
        raise AssertionError("道路网络版本应为正整数")
    nodes_by_id = _exact_unique_map(
        route.get("network_nodes"),
        id_key="node_id",
        expected_ids={f"N{index:02d}" for index in range(1, 19)},
        label="道路节点",
    )
    edges_by_id = _exact_unique_map(
        route.get("network_edges"),
        id_key="edge_id",
        expected_ids={f"E{index:02d}" for index in range(1, 27)},
        label="道路边",
    )
    for edge_id, edge in edges_by_id.items():
        if edge.get("from_node_id") not in nodes_by_id or edge.get("to_node_id") not in nodes_by_id:
            raise AssertionError(f"{edge_id} 引用了不存在的道路节点")
    _verify_path_topology(
        original,
        expected_nodes=["N01", "N02", "N03", "N04", "N05", "N06"],
        expected_edges=["E01", "E02", "E03", "E04", "E05"],
        edges_by_id=edges_by_id,
        label="原路线",
    )
    _verify_path_topology(
        recommended,
        expected_nodes=["N01", "N02", "N07", "N08", "N09", "N06"],
        expected_edges=["E01", "E06", "E07", "E08", "E09"],
        edges_by_id=edges_by_id,
        label="新路线",
    )
    _expect(edges_by_id["E04"].get("status"), "BLOCKED", "堵塞道路状态")
    return {
        "task_id": result["task_id"],
        "algorithm": "DIJKSTRA_V1",
        "road_network_version": network_version,
        "nodes": 18,
        "edges": 26,
    }


async def run(base_url: str, timeout_seconds: float) -> dict[str, Any]:
    token = os.environ.get("E2E_ACCESS_TOKEN", "").strip()
    if not token:
        raise RuntimeError("缺少 E2E_ACCESS_TOKEN；令牌必须通过环境变量传入")
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(base_url=base_url.rstrip("/"), headers=headers, timeout=10.0) as client:
        breakdown_order, blocked_order = await asyncio.gather(
            _resolve_order(client, "DEMO-ORDER-001"),
            _resolve_order(client, "DEMO-ORDER-005"),
        )
        breakdown_task, breakdown = await _submit_and_wait(
            client,
            order=breakdown_order,
            anomaly_type="VEHICLE_BREAKDOWN",
            description="V-001 发动机故障，无法继续配送，请计算替代车辆与接驳路线。",
            vehicle_status="BROKEN",
            idempotency_key="task9-offline-breakdown-v1",
            timeout_seconds=timeout_seconds,
        )
        blocked_task, blocked = await _submit_and_wait(
            client,
            order=blocked_order,
            anomaly_type="ROAD_BLOCKED",
            description="新平路东河桥段 E04 塌方阻断，请重新计算可行路线。",
            vehicle_status="NORMAL",
            idempotency_key="task9-offline-road-blocked-v1",
            timeout_seconds=timeout_seconds,
        )
    breakdown_summary = _verify_breakdown(breakdown)
    blocked_summary = _verify_blocked(blocked)
    _expect(breakdown_summary["task_id"], breakdown_task, "故障任务身份")
    _expect(blocked_summary["task_id"], blocked_task, "堵塞任务身份")
    return {"passed": True, "mode": "REAL_PUBLIC_API", "breakdown": breakdown_summary, "road_blocked": blocked_summary}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8001")
    parser.add_argument("--timeout-seconds", type=float, default=45.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        payload = asyncio.run(run(args.base_url, args.timeout_seconds))
    except (AssertionError, RuntimeError, TypeError, httpx.HTTPError) as error:
        print(f"[FAIL] 离线车辆与路线公开 API 验收失败：{error}")
        raise SystemExit(1) from error
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)


if __name__ == "__main__":
    main()
