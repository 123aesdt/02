from dataclasses import dataclass

from app.graph_memory.models import EntityType, GraphEntity, GraphRelation, RelationType


@dataclass(frozen=True)
class GraphMemoryContext:
    driver_id: str
    route_id: str
    anomaly_type: str
    text: str
    vehicle_id: str | None = None
    weather: str | None = None


@dataclass(frozen=True)
class GraphExtraction:
    entities: tuple[GraphEntity, ...]
    relations: tuple[GraphRelation, ...]


class DeterministicGraphTripleExtractor:
    def extract(self, context: GraphMemoryContext) -> GraphExtraction:
        driver = GraphEntity(EntityType.DRIVER, context.driver_id, self._name(context.text, "李师傅", context.driver_id))
        route = GraphEntity(EntityType.ROUTE, context.route_id, self._name(context.text, "新平路", context.route_id))
        anomaly_id = context.anomaly_type.replace("_", "-")
        anomaly_name = "雨天湿滑" if "湿滑" in context.text else context.anomaly_type
        anomaly = GraphEntity(EntityType.ANOMALY, anomaly_id, anomaly_name)
        entities: list[GraphEntity] = [driver, route, anomaly]
        relations: list[GraphRelation] = [
            GraphRelation(driver, RelationType.SERVES, route, source_type="deterministic_extraction", evidence=context.text),
        ]

        if context.vehicle_id:
            vehicle_name = self._name(context.text, "冷链车A", context.vehicle_id)
            vehicle = GraphEntity(EntityType.VEHICLE, context.vehicle_id, vehicle_name)
            entities.append(vehicle)
            relations.append(
                GraphRelation(driver, RelationType.DRIVES, vehicle, source_type="deterministic_extraction", evidence=context.text)
            )

        weather_id = self._weather_id(context)
        if weather_id:
            weather_name = "雨天" if weather_id == "rain" else weather_id
            weather = GraphEntity(EntityType.WEATHER, weather_id, weather_name)
            entities.append(weather)
            relations.extend(
                (
                    GraphRelation(route, RelationType.AFFECTED_BY, weather, source_type="deterministic_extraction", evidence=context.text),
                    GraphRelation(anomaly, RelationType.AFFECTED_BY, weather, source_type="deterministic_extraction", evidence=context.text),
                )
            )
        return GraphExtraction(tuple(entities), tuple(relations))

    @staticmethod
    def _name(text: str, expected_name: str, fallback: str) -> str:
        return expected_name if expected_name in text else fallback

    @staticmethod
    def _weather_id(context: GraphMemoryContext) -> str | None:
        weather = (context.weather or "").lower()
        if "雨" in context.text or weather in {"rain", "heavy_rain", "rainy"}:
            return "rain"
        return context.weather

