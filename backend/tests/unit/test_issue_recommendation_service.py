import pytest

from app.recommendations.service import IssueRecommendationService


@pytest.mark.parametrize(
    ("anomaly_type", "description", "category", "subtype", "action_fragment"),
    [
        ("VEHICLE_BREAKDOWN", "右后轮爆胎，车辆无法继续行驶", "VEHICLE_BREAKDOWN", "TIRE", "更换轮胎"),
        ("ROAD_BLOCKED", "前方塌方封路", "ROAD_BLOCKED", "LANDSLIDE", "等待调度"),
        ("WEATHER", "暴雨导致能见度低", "WEATHER", "HEAVY_RAIN", "暂缓通行"),
        ("CARGO", "冷链货物温度异常", "CARGO", "TEMPERATURE", "检查"),
        ("CAPACITY", "车辆超载无法继续配送", "CAPACITY", "OVERLOAD", "转运"),
        ("OTHER", "现场出现未分类问题", "OTHER", "GENERAL", "联系调度员"),
    ],
)
def test_recommendation_maps_real_incident_to_non_empty_action(
    anomaly_type: str,
    description: str,
    category: str,
    subtype: str,
    action_fragment: str,
) -> None:
    result = IssueRecommendationService().recommend(
        anomaly_type=anomaly_type,
        anomaly_description=description,
        vehicle_status="BROKEN" if category == "VEHICLE_BREAKDOWN" else "NORMAL",
        environment_risk="HIGH",
        capacity_status="UNAVAILABLE" if category == "CAPACITY" else "AVAILABLE",
        candidate_routes=[],
        recommended_route=None,
    )

    assert (result.issue_category, result.issue_subtype) == (category, subtype)
    assert action_fragment in result.recommended_action
    assert description in result.analysis_reason
    assert result.recommended_route is None
    assert result.analysis_mode == "EIGHT_AGENT_RULE_ASSISTED"


def test_tire_incident_rejects_a_route_even_when_routing_returned_one() -> None:
    result = IssueRecommendationService().recommend(
        anomaly_type="VEHICLE_BREAKDOWN",
        anomaly_description="轮胎被扎破",
        vehicle_status="BROKEN",
        environment_risk="LOW",
        capacity_status="UNAVAILABLE",
        candidate_routes=[{"route_id": "route-safe", "available": True}],
        recommended_route="route-safe",
    )

    assert result.issue_subtype == "TIRE"
    assert result.recommended_route is None
    assert "安全停车" in result.recommended_action
    assert "更换轮胎" in result.recommended_action


def test_road_blockage_keeps_only_an_available_provider_candidate() -> None:
    service = IssueRecommendationService()

    available = service.recommend(
        anomaly_type="ROAD_BLOCKED",
        anomaly_description="道路施工封闭",
        vehicle_status="NORMAL",
        environment_risk="HIGH",
        capacity_status="AVAILABLE",
        candidate_routes=[{"route_id": "route-safe", "available": True}],
        recommended_route="route-safe",
    )
    unavailable = service.recommend(
        anomaly_type="ROAD_BLOCKED",
        anomaly_description="道路施工封闭",
        vehicle_status="NORMAL",
        environment_risk="HIGH",
        capacity_status="AVAILABLE",
        candidate_routes=[{"route_id": "route-closed", "available": False}],
        recommended_route="route-closed",
    )

    assert available.recommended_route == "route-safe"
    assert "按已核验的安全候选路线改道" in available.recommended_action
    assert unavailable.recommended_route is None
    assert "等待调度" in unavailable.recommended_action


def test_unknown_structured_type_uses_description_as_secondary_signal() -> None:
    result = IssueRecommendationService().recommend(
        anomaly_type="UNRECOGNIZED",
        anomaly_description="刹车失灵，车辆无法制动",
        vehicle_status="BROKEN",
        environment_risk=None,
        capacity_status=None,
        candidate_routes=[],
        recommended_route=None,
    )

    assert result.issue_category == "VEHICLE_BREAKDOWN"
    assert result.issue_subtype == "BRAKE"
    assert "道路救援" in result.recommended_action
