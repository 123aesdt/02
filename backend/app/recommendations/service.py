from collections.abc import Mapping, Sequence

from app.recommendations.models import IssueRecommendation

KNOWN_CATEGORIES = {
    "VEHICLE_BREAKDOWN",
    "ROAD_BLOCKED",
    "ROAD_HAZARD",
    "WEATHER",
    "CARGO",
    "CAPACITY",
    "OTHER",
}

NON_ROUTE_CATEGORIES = {"VEHICLE_BREAKDOWN", "CARGO", "CAPACITY", "OTHER"}


class IssueRecommendationService:
    def recommend(
        self,
        *,
        anomaly_type: str,
        anomaly_description: str,
        vehicle_status: str | None,
        environment_risk: str | None,
        capacity_status: str | None,
        candidate_routes: Sequence[Mapping[str, object]],
        recommended_route: str | None,
    ) -> IssueRecommendation:
        description = anomaly_description.strip() or "现场异常描述缺失"
        category = self._normalize_category(anomaly_type, description)
        subtype = self._identify_subtype(category, description)
        route = None
        if category not in NON_ROUTE_CATEGORIES:
            route = self._verified_route(recommended_route, candidate_routes)
        return IssueRecommendation(
            issue_category=category,
            issue_subtype=subtype,
            analysis_reason=self._reason(
                description=description,
                vehicle_status=vehicle_status,
                environment_risk=environment_risk,
                capacity_status=capacity_status,
            ),
            recommended_action=self._action(category, subtype, route),
            recommended_route=route,
        )

    @staticmethod
    def _normalize_category(anomaly_type: str, description: str) -> str:
        normalized = anomaly_type.strip().upper()
        aliases = {
            "ROAD": "ROAD_HAZARD",
            "VEHICLE": "VEHICLE_BREAKDOWN",
            "VEHICLE_FAULT": "VEHICLE_BREAKDOWN",
            "GOODS": "CARGO",
        }
        category = aliases.get(normalized, normalized)
        if category in KNOWN_CATEGORIES:
            return category
        if IssueRecommendationService._contains(description, "爆胎", "轮胎", "扎胎", "刹车", "制动", "发动机", "车辆故障"):
            return "VEHICLE_BREAKDOWN"
        if IssueRecommendationService._contains(description, "封路", "道路封闭", "塌方"):
            return "ROAD_BLOCKED"
        if IssueRecommendationService._contains(description, "湿滑", "坑洼", "落石", "道路损坏"):
            return "ROAD_HAZARD"
        if IssueRecommendationService._contains(description, "暴雨", "大雪", "大雾", "强风", "天气"):
            return "WEATHER"
        if IssueRecommendationService._contains(description, "货物", "泄漏", "温控", "冷链", "倾斜"):
            return "CARGO"
        if IssueRecommendationService._contains(description, "超载", "司机不可用", "车辆不可用", "运力"):
            return "CAPACITY"
        return "OTHER"

    @staticmethod
    def _identify_subtype(category: str, description: str) -> str:
        rules: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
            "VEHICLE_BREAKDOWN": (
                ("TIRE", ("爆胎", "轮胎", "扎胎")),
                ("BRAKE", ("刹车", "制动")),
                ("ENGINE", ("发动机", "引擎")),
            ),
            "ROAD_BLOCKED": (
                ("LANDSLIDE", ("塌方", "滑坡")),
                ("FLOODING", ("积水", "淹水")),
                ("CONSTRUCTION", ("施工",)),
                ("CLOSURE", ("封路", "封闭")),
            ),
            "ROAD_HAZARD": (
                ("SLIPPERY", ("湿滑", "结冰")),
                ("POTHOLE", ("坑洼", "坑洞")),
                ("ROCKFALL", ("落石",)),
                ("DAMAGE", ("道路损坏", "路面破损")),
            ),
            "WEATHER": (
                ("HEAVY_RAIN", ("暴雨", "强降雨")),
                ("SNOW", ("大雪", "暴雪")),
                ("FOG", ("大雾", "能见度低")),
                ("STRONG_WIND", ("强风", "大风")),
            ),
            "CARGO": (
                ("TEMPERATURE", ("温控", "温度", "冷链")),
                ("LEAK", ("泄漏", "渗漏")),
                ("DAMAGE", ("破损",)),
                ("SHIFT", ("倾斜", "移位")),
            ),
            "CAPACITY": (
                ("OVERLOAD", ("超载",)),
                ("DRIVER_UNAVAILABLE", ("司机不可用",)),
                ("VEHICLE_UNAVAILABLE", ("车辆不可用",)),
            ),
        }
        for subtype, keywords in rules.get(category, ()):
            if IssueRecommendationService._contains(description, *keywords):
                return subtype
        return "GENERAL"

    @staticmethod
    def _verified_route(
        recommended_route: str | None,
        candidate_routes: Sequence[Mapping[str, object]],
    ) -> str | None:
        if not recommended_route:
            return None
        for candidate in candidate_routes:
            if candidate.get("route_id") == recommended_route and candidate.get("available") is True:
                return recommended_route
        return None

    @staticmethod
    def _reason(
        *,
        description: str,
        vehicle_status: str | None,
        environment_risk: str | None,
        capacity_status: str | None,
    ) -> str:
        facts = [f"员工上报“{description}”"]
        if vehicle_status:
            facts.append(f"车辆状态为 {vehicle_status}")
        if environment_risk:
            facts.append(f"环境风险为 {environment_risk}")
        if capacity_status:
            facts.append(f"运力状态为 {capacity_status}")
        return "；".join(facts) + "，8-Agent 协同分析后需要执行安全处置。"

    @staticmethod
    def _action(category: str, subtype: str, route: str | None) -> str:
        if category == "VEHICLE_BREAKDOWN":
            if subtype == "TIRE":
                return "立即安全停车并设置警示标志，检查备胎条件；可安全操作时更换轮胎，否则联系道路救援，必要时换车转运。"
            if subtype == "BRAKE":
                return "立即停止继续行驶并设置警示标志，联系道路救援检修制动系统，必要时换车转运。"
            if subtype == "ENGINE":
                return "立即安全停车并关闭车辆，联系道路救援检查发动机，确认修复前不得继续配送。"
            return "立即安全停车并设置警示标志，联系道路救援检查车辆，必要时换车转运。"
        if category == "ROAD_BLOCKED":
            return (
                "保持安全距离，按已核验的安全候选路线改道并服从调度指令。"
                if route
                else "停在安全位置并保持任务暂停，等待调度核实后配置替代路线。"
            )
        if category == "ROAD_HAZARD":
            return (
                "降低车速并按已核验的安全候选路线绕行，持续关注现场路况。"
                if route
                else "立即降速并在必要时停止通行，上报准确位置，等待调度核实安全路线。"
            )
        if category == "WEATHER":
            return (
                "暂缓当前路线通行，确认安全后按已核验候选路线改道。"
                if route
                else "暂缓通行并就近安全避险，等待环境风险下降或调度确认替代路线。"
            )
        if category == "CARGO":
            return "立即安全停车检查货物，隔离泄漏或温控风险，重新固定货物，必要时安排转运。"
        if category == "CAPACITY":
            return "保持任务暂停并重新分配司机或车辆；存在超载时立即卸载分流，必要时拆单转运。"
        return "保持任务暂停，记录现场位置和现象，并立即联系调度员补充资源与处置方案。"

    @staticmethod
    def _contains(value: str, *keywords: str) -> bool:
        return any(keyword in value for keyword in keywords)
