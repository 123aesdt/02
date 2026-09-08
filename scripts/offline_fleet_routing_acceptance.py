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
    _expect(pickup.get("edge_ids"), ["E20"], "接驳道路")
    _expect(pickup.get("distance_km"), "2.80", "接驳距离")
    _expect(pickup.get("estimated_minutes"), 6, "接驳耗时")
    candidates = _list(allocation.get("candidate_vehicles"), "候选车辆")
    _expect(len(candidates), 12, "候选车辆总数")
    by_id = {str(item.get("vehicle_id")): _object(item, "候选车辆项") for item in candidates}
    _expect(by_id["V-005"].get("score"), "93.4", "V-005 总分")
    unexplained = [
        vehicle_id
        for vehicle_id, item in by_id.items()
        if item.get("eligible") is not True and not _list(item.get("exclusion_reasons"), f"{vehicle_id} 排除原因")
    ]
    _expect(unexplained, [], "全部未入选车辆均有排除原因")
    return {"task_id": result["task_id"], "candidate_count": len(candidates), "selected_score": "93.4"}


def _verify_blocked(result: dict[str, Any]) -> dict[str, Any]:
    route = _object(result.get("route_plan"), "路线重算证据")
    original = _object(route.get("original_path"), "原路线")
    recommended = _object(route.get("recommended_path"), "新路线")
    _expect(original.get("edge_ids"), ["E01", "E02", "E03", "E04", "E05"], "原道路序列")
    _expect(recommended.get("edge_ids"), ["E01", "E06", "E07", "E08", "E09"], "新道路序列")
    if "E04" in _list(recommended.get("edge_ids"), "新道路序列"):
        raise AssertionError("新路线仍包含堵塞边 E04")
    _expect(route.get("blocked_edge_ids"), ["E04"], "堵塞边")
    _expect(route.get("distance_delta_km"), "3.20", "里程增量")
    _expect(route.get("eta_delta_minutes"), 4, "耗时增量")
    _expect(route.get("algorithm"), "DIJKSTRA_V1", "路径算法")
    network_version = route.get("road_network_version")
    if not isinstance(network_version, int) or isinstance(network_version, bool) or network_version < 1:
        raise AssertionError("道路网络版本应为正整数")
    _expect(len(_list(route.get("network_nodes"), "道路节点")), 18, "道路节点数")
    _expect(len(_list(route.get("network_edges"), "道路边")), 26, "道路边数")
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
