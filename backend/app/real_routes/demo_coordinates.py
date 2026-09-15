from decimal import Decimal
from types import MappingProxyType

from app.real_routes.models import GeoPoint

MAPPING_VERSION = "DEMO_AMAP_V1"

_NODE_COORDINATES = MappingProxyType(
    {
        "N01": ("103.044800", "25.226500"),
        "N02": ("103.032000", "25.232000"),
        "N03": ("103.057000", "25.239000"),
        "N04": ("103.079000", "25.246000"),
        "N05": ("103.104000", "25.252000"),
        "N06": ("103.135000", "25.261000"),
        "N07": ("103.018000", "25.207000"),
        "N08": ("103.062000", "25.198000"),
        "N09": ("103.105000", "25.214000"),
        "N10": ("103.025000", "25.267000"),
        "N11": ("103.013000", "25.303000"),
        "N12": ("102.973000", "25.247000"),
        "N13": ("103.072000", "25.158000"),
        "N14": ("102.991000", "25.217000"),
        "N15": ("103.077000", "25.228000"),
        "N16": ("102.997000", "25.279000"),
        "N17": ("103.132000", "25.293000"),
        "N18": ("103.151000", "25.204000"),
        "N19": ("103.051000", "25.220000"),
        "N20": ("103.092000", "25.235000"),
        "N21": ("103.117000", "25.225000"),
        "N22": ("103.069000", "25.231000"),
    }
)


def demo_geo_point(node_id: str) -> GeoPoint:
    try:
        longitude, latitude = _NODE_COORDINATES[node_id]
    except KeyError as error:
        raise ValueError(f"虚拟路线节点没有高德坐标映射: {node_id}") from error
    return GeoPoint(node_id, Decimal(longitude), Decimal(latitude))


def demo_geo_points(node_ids: tuple[str, ...]) -> tuple[GeoPoint, ...]:
    return tuple(demo_geo_point(node_id) for node_id in node_ids)
