from types import MappingProxyType

STATIONS = (
    MappingProxyType(
        {"station_id": "ST-001", "name": "新平县中心仓", "station_type": "HUB", "road_node_id": "N01", "handling_capacity_kg": "20000.00", "status": "ACTIVE"}
    ),
    MappingProxyType(
        {"station_id": "ST-002", "name": "城东配送站", "station_type": "TOWN", "road_node_id": "N06", "handling_capacity_kg": "6000.00", "status": "ACTIVE"}
    ),
    MappingProxyType(
        {"station_id": "ST-003", "name": "北岭村驿站", "station_type": "VILLAGE", "road_node_id": "N11", "handling_capacity_kg": "1200.00", "status": "ACTIVE"}
    ),
    MappingProxyType(
        {"station_id": "ST-004", "name": "河西乡服务站", "station_type": "TOWN", "road_node_id": "N12", "handling_capacity_kg": "3500.00", "status": "ACTIVE"}
    ),
    MappingProxyType(
        {
            "station_id": "ST-005",
            "name": "南山村服务点",
            "station_type": "VILLAGE",
            "road_node_id": "N13",
            "handling_capacity_kg": "1000.00",
            "status": "ACTIVE",
        }
    ),
    MappingProxyType(
        {
            "station_id": "ST-006",
            "name": "新平冷链中心",
            "station_type": "COLD_CHAIN",
            "road_node_id": "N14",
            "handling_capacity_kg": "5000.00",
            "status": "ACTIVE",
        }
    ),
    MappingProxyType(
        {
            "station_id": "ST-007",
            "name": "县域车辆维修站",
            "station_type": "MAINTENANCE",
            "road_node_id": "N15",
            "handling_capacity_kg": "2500.00",
            "status": "ACTIVE",
        }
    ),
    MappingProxyType(
        {"station_id": "ST-008", "name": "城东电商服务点", "station_type": "TOWN", "road_node_id": "N17", "handling_capacity_kg": "2800.00", "status": "ACTIVE"}
    ),
)

ROAD_NODES = (
    MappingProxyType({"node_id": "N01", "name": "新平县中心仓", "x_km": "0.00", "y_km": "0.00", "node_type": "STATION"}),
    MappingProxyType({"node_id": "N02", "name": "西环路口", "x_km": "2.00", "y_km": "0.00", "node_type": "JUNCTION"}),
    MappingProxyType({"node_id": "N03", "name": "新平路西口", "x_km": "2.00", "y_km": "2.00", "node_type": "JUNCTION"}),
    MappingProxyType({"node_id": "N04", "name": "新平路 K3.2", "x_km": "5.00", "y_km": "2.00", "node_type": "INCIDENT_POINT"}),
    MappingProxyType({"node_id": "N05", "name": "东河桥", "x_km": "8.00", "y_km": "2.00", "node_type": "BRIDGE"}),
    MappingProxyType({"node_id": "N06", "name": "城东配送站", "x_km": "10.00", "y_km": "2.00", "node_type": "STATION"}),
    MappingProxyType({"node_id": "N07", "name": "102 国道西口", "x_km": "2.00", "y_km": "-2.00", "node_type": "JUNCTION"}),
    MappingProxyType({"node_id": "N08", "name": "102 国道中段", "x_km": "6.00", "y_km": "-2.00", "node_type": "JUNCTION"}),
    MappingProxyType({"node_id": "N09", "name": "102 国道东口", "x_km": "9.00", "y_km": "-1.00", "node_type": "JUNCTION"}),
    MappingProxyType({"node_id": "N10", "name": "308 县道口", "x_km": "0.00", "y_km": "3.00", "node_type": "JUNCTION"}),
    MappingProxyType({"node_id": "N11", "name": "北岭村驿站", "x_km": "4.00", "y_km": "6.00", "node_type": "STATION"}),
    MappingProxyType({"node_id": "N12", "name": "河西乡服务站", "x_km": "-3.00", "y_km": "2.00", "node_type": "STATION"}),
    MappingProxyType({"node_id": "N13", "name": "南山村服务点", "x_km": "7.00", "y_km": "-5.00", "node_type": "STATION"}),
    MappingProxyType({"node_id": "N14", "name": "新平冷链中心", "x_km": "1.00", "y_km": "-1.00", "node_type": "STATION"}),
    MappingProxyType({"node_id": "N15", "name": "县域车辆维修站", "x_km": "4.00", "y_km": "1.00", "node_type": "STATION"}),
    MappingProxyType({"node_id": "N16", "name": "河西农资路口", "x_km": "-1.00", "y_km": "4.00", "node_type": "JUNCTION"}),
    MappingProxyType({"node_id": "N17", "name": "城东电商服务点", "x_km": "11.00", "y_km": "4.00", "node_type": "STATION"}),
    MappingProxyType({"node_id": "N18", "name": "双河村路口", "x_km": "12.00", "y_km": "0.00", "node_type": "JUNCTION"}),
)

ROAD_EDGES = (
    MappingProxyType(
        {
            "edge_id": "E01",
            "name": "中心仓连接线",
            "from_node_id": "N01",
            "to_node_id": "N02",
            "distance_km": "1.50",
            "base_minutes": 3,
            "road_level": "COUNTY",
            "risk_level": "LOW",
            "weight_limit_tons": "8.00",
        }
    ),
    MappingProxyType(
        {
            "edge_id": "E02",
            "name": "西环至新平路",
            "from_node_id": "N02",
            "to_node_id": "N03",
            "distance_km": "1.50",
            "base_minutes": 3,
            "road_level": "COUNTY",
            "risk_level": "LOW",
            "weight_limit_tons": "8.00",
        }
    ),
    MappingProxyType(
        {
            "edge_id": "E03",
            "name": "新平路西段",
            "from_node_id": "N03",
            "to_node_id": "N04",
            "distance_km": "2.00",
            "base_minutes": 4,
            "road_level": "COUNTY",
            "risk_level": "MEDIUM",
            "weight_limit_tons": "6.00",
        }
    ),
    MappingProxyType(
        {
            "edge_id": "E04",
            "name": "新平路东河桥段",
            "from_node_id": "N04",
            "to_node_id": "N05",
            "distance_km": "2.50",
            "base_minutes": 5,
            "road_level": "COUNTY",
            "risk_level": "HIGH",
            "weight_limit_tons": "6.00",
        }
    ),
    MappingProxyType(
        {
            "edge_id": "E05",
            "name": "东河桥连接线",
            "from_node_id": "N05",
            "to_node_id": "N06",
            "distance_km": "2.50",
            "base_minutes": 5,
            "road_level": "TOWN",
            "risk_level": "LOW",
            "weight_limit_tons": "5.00",
        }
    ),
    MappingProxyType(
        {
            "edge_id": "E06",
            "name": "102 国道引道",
            "from_node_id": "N02",
            "to_node_id": "N07",
            "distance_km": "2.00",
            "base_minutes": 4,
            "road_level": "COUNTY",
            "risk_level": "LOW",
            "weight_limit_tons": "10.00",
        }
    ),
    MappingProxyType(
        {
            "edge_id": "E07",
            "name": "102 国道西段",
            "from_node_id": "N07",
            "to_node_id": "N08",
            "distance_km": "4.00",
            "base_minutes": 7,
            "road_level": "NATIONAL",
            "risk_level": "LOW",
            "weight_limit_tons": "20.00",
        }
    ),
    MappingProxyType(
        {
            "edge_id": "E08",
            "name": "102 国道东段",
            "from_node_id": "N08",
            "to_node_id": "N09",
            "distance_km": "3.20",
            "base_minutes": 6,
            "road_level": "NATIONAL",
            "risk_level": "LOW",
            "weight_limit_tons": "20.00",
        }
    ),
    MappingProxyType(
        {
            "edge_id": "E09",
            "name": "国道至城东站",
            "from_node_id": "N09",
            "to_node_id": "N06",
            "distance_km": "2.50",
            "base_minutes": 4,
            "road_level": "COUNTY",
            "risk_level": "LOW",
            "weight_limit_tons": "8.00",
        }
    ),
    MappingProxyType(
        {
            "edge_id": "E10",
            "name": "中心仓至 308 线",
            "from_node_id": "N01",
            "to_node_id": "N10",
            "distance_km": "3.10",
            "base_minutes": 6,
            "road_level": "COUNTY",
            "risk_level": "MEDIUM",
            "weight_limit_tons": "8.00",
        }
    ),
    MappingProxyType(
        {
            "edge_id": "E11",
            "name": "308 县道北岭段",
            "from_node_id": "N10",
            "to_node_id": "N11",
            "distance_km": "5.50",
            "base_minutes": 11,
            "road_level": "COUNTY",
            "risk_level": "MEDIUM",
            "weight_limit_tons": "5.00",
        }
    ),
    MappingProxyType(
        {
            "edge_id": "E12",
            "name": "308 县道农资段",
            "from_node_id": "N10",
            "to_node_id": "N16",
            "distance_km": "2.00",
            "base_minutes": 4,
            "road_level": "COUNTY",
            "risk_level": "LOW",
            "weight_limit_tons": "7.00",
        }
    ),
    MappingProxyType(
        {
            "edge_id": "E13",
            "name": "河西农资支线",
            "from_node_id": "N16",
            "to_node_id": "N12",
            "distance_km": "4.00",
            "base_minutes": 8,
            "road_level": "TOWN",
            "risk_level": "LOW",
            "weight_limit_tons": "5.00",
        }
    ),
    MappingProxyType(
        {
            "edge_id": "E14",
            "name": "河西回仓线",
            "from_node_id": "N12",
            "to_node_id": "N01",
            "distance_km": "3.60",
            "base_minutes": 7,
            "road_level": "TOWN",
            "risk_level": "LOW",
            "weight_limit_tons": "5.00",
        }
    ),
    MappingProxyType(
        {
            "edge_id": "E15",
            "name": "102 国道南山支线",
            "from_node_id": "N08",
            "to_node_id": "N13",
            "distance_km": "4.50",
            "base_minutes": 9,
            "road_level": "VILLAGE",
            "risk_level": "MEDIUM",
            "weight_limit_tons": "3.50",
        }
    ),
    MappingProxyType(
        {
            "edge_id": "E16",
            "name": "南山东接线",
            "from_node_id": "N13",
            "to_node_id": "N09",
            "distance_km": "5.20",
            "base_minutes": 10,
            "road_level": "VILLAGE",
            "risk_level": "MEDIUM",
            "weight_limit_tons": "3.50",
        }
    ),
    MappingProxyType(
        {
            "edge_id": "E17",
            "name": "城东电商北线",
            "from_node_id": "N06",
            "to_node_id": "N17",
            "distance_km": "3.50",
            "base_minutes": 7,
            "road_level": "TOWN",
            "risk_level": "LOW",
            "weight_limit_tons": "5.00",
        }
    ),
    MappingProxyType(
        {
            "edge_id": "E18",
            "name": "电商双河线",
            "from_node_id": "N17",
            "to_node_id": "N18",
            "distance_km": "4.00",
            "base_minutes": 8,
            "road_level": "VILLAGE",
            "risk_level": "LOW",
            "weight_limit_tons": "3.50",
        }
    ),
    MappingProxyType(
        {
            "edge_id": "E19",
            "name": "双河城东线",
            "from_node_id": "N18",
            "to_node_id": "N06",
            "distance_km": "2.80",
            "base_minutes": 6,
            "road_level": "VILLAGE",
            "risk_level": "LOW",
            "weight_limit_tons": "3.50",
        }
    ),
    MappingProxyType(
        {
            "edge_id": "E20",
            "name": "维修站接驳线",
            "from_node_id": "N15",
            "to_node_id": "N04",
            "distance_km": "2.80",
            "base_minutes": 6,
            "road_level": "TOWN",
            "risk_level": "LOW",
            "weight_limit_tons": "5.00",
        }
    ),
    MappingProxyType(
        {
            "edge_id": "E21",
            "name": "维修站国道线",
            "from_node_id": "N15",
            "to_node_id": "N08",
            "distance_km": "3.00",
            "base_minutes": 6,
            "road_level": "COUNTY",
            "risk_level": "LOW",
            "weight_limit_tons": "8.00",
        }
    ),
    MappingProxyType(
        {
            "edge_id": "E22",
            "name": "冷链中心回仓线",
            "from_node_id": "N14",
            "to_node_id": "N01",
            "distance_km": "1.10",
            "base_minutes": 3,
            "road_level": "TOWN",
            "risk_level": "LOW",
            "weight_limit_tons": "5.00",
        }
    ),
    MappingProxyType(
        {
            "edge_id": "E23",
            "name": "冷链中心国道线",
            "from_node_id": "N14",
            "to_node_id": "N07",
            "distance_km": "2.50",
            "base_minutes": 5,
            "road_level": "COUNTY",
            "risk_level": "LOW",
            "weight_limit_tons": "8.00",
        }
    ),
    MappingProxyType(
        {
            "edge_id": "E24",
            "name": "北岭电商山路",
            "from_node_id": "N11",
            "to_node_id": "N17",
            "distance_km": "8.00",
            "base_minutes": 15,
            "road_level": "VILLAGE",
            "risk_level": "HIGH",
            "weight_limit_tons": "2.00",
        }
    ),
    MappingProxyType(
        {
            "edge_id": "E25",
            "name": "东河桥电商线",
            "from_node_id": "N05",
            "to_node_id": "N17",
            "distance_km": "3.10",
            "base_minutes": 6,
            "road_level": "TOWN",
            "risk_level": "LOW",
            "weight_limit_tons": "5.00",
        }
    ),
    MappingProxyType(
        {
            "edge_id": "E26",
            "name": "国道双河线",
            "from_node_id": "N09",
            "to_node_id": "N18",
            "distance_km": "3.30",
            "base_minutes": 6,
            "road_level": "COUNTY",
            "risk_level": "LOW",
            "weight_limit_tons": "8.00",
        }
    ),
)

DRIVERS = (
    MappingProxyType(
        {"driver_id": "D-001", "name": "李师傅", "license_class": "C1", "status": "BUSY", "current_vehicle_id": "V-001", "current_node_id": "N04"}
    ),
    MappingProxyType(
        {"driver_id": "D-002", "name": "张师傅", "license_class": "C1", "status": "ON_DUTY", "current_vehicle_id": "V-002", "current_node_id": "N01"}
    ),
    MappingProxyType(
        {"driver_id": "D-003", "name": "陈师傅", "license_class": "C1", "status": "ON_DUTY", "current_vehicle_id": "V-005", "current_node_id": "N15"}
    ),
    MappingProxyType(
        {"driver_id": "D-004", "name": "王师傅", "license_class": "B2", "status": "BUSY", "current_vehicle_id": "V-004", "current_node_id": "N06"}
    ),
    MappingProxyType(
        {"driver_id": "D-005", "name": "林师傅", "license_class": "C1", "status": "OFF_DUTY", "current_vehicle_id": "V-006", "current_node_id": "N14"}
    ),
    MappingProxyType(
        {"driver_id": "D-006", "name": "黄师傅", "license_class": "C1", "status": "ON_DUTY", "current_vehicle_id": "V-007", "current_node_id": "N12"}
    ),
    MappingProxyType(
        {"driver_id": "D-007", "name": "周师傅", "license_class": "B2", "status": "ON_DUTY", "current_vehicle_id": "V-008", "current_node_id": "N03"}
    ),
    MappingProxyType(
        {"driver_id": "D-008", "name": "徐师傅", "license_class": "C1", "status": "BUSY", "current_vehicle_id": "V-009", "current_node_id": "N11"}
    ),
    MappingProxyType(
        {"driver_id": "D-009", "name": "郭师傅", "license_class": "B2", "status": "ON_DUTY", "current_vehicle_id": "V-010", "current_node_id": "N01"}
    ),
    MappingProxyType(
        {"driver_id": "D-010", "name": "杨师傅", "license_class": "C1", "status": "ON_DUTY", "current_vehicle_id": "V-012", "current_node_id": "N06"}
    ),
)

VEHICLES = (
    MappingProxyType(
        {
            "vehicle_id": "V-001",
            "plate_no": "新物冷链-01",
            "vehicle_type": "REFRIGERATED_VAN",
            "max_load_kg": "1500.00",
            "current_load_kg": "700.00",
            "gross_weight_tons": "2.80",
            "cargo_capability": "COLD_CHAIN",
            "status": "IN_TRANSIT",
            "current_node_id": "N04",
            "assigned_driver_id": "D-001",
        }
    ),
    MappingProxyType(
        {
            "vehicle_id": "V-002",
            "plate_no": "新物厢货-02",
            "vehicle_type": "VAN",
            "max_load_kg": "1200.00",
            "current_load_kg": "200.00",
            "gross_weight_tons": "2.20",
            "cargo_capability": "GENERAL",
            "status": "AVAILABLE",
            "current_node_id": "N01",
            "assigned_driver_id": "D-002",
        }
    ),
    MappingProxyType(
        {
            "vehicle_id": "V-003",
            "plate_no": "新物厢货-03",
            "vehicle_type": "VAN",
            "max_load_kg": "1000.00",
            "current_load_kg": "600.00",
            "gross_weight_tons": "2.00",
            "cargo_capability": "GENERAL",
            "status": "AVAILABLE",
            "current_node_id": "N15",
            "assigned_driver_id": None,
        }
    ),
    MappingProxyType(
        {
            "vehicle_id": "V-004",
            "plate_no": "新物轻卡-04",
            "vehicle_type": "LIGHT_TRUCK",
            "max_load_kg": "3000.00",
            "current_load_kg": "1200.00",
            "gross_weight_tons": "5.50",
            "cargo_capability": "FARM_SUPPLY",
            "status": "IN_TRANSIT",
            "current_node_id": "N06",
            "assigned_driver_id": "D-004",
        }
    ),
    MappingProxyType(
        {
            "vehicle_id": "V-005",
            "plate_no": "新物冷链-05",
            "vehicle_type": "REFRIGERATED_VAN",
            "max_load_kg": "1000.00",
            "current_load_kg": "100.00",
            "gross_weight_tons": "2.40",
            "cargo_capability": "COLD_CHAIN",
            "status": "AVAILABLE",
            "current_node_id": "N15",
            "assigned_driver_id": "D-003",
        }
    ),
    MappingProxyType(
        {
            "vehicle_id": "V-006",
            "plate_no": "新物电运-06",
            "vehicle_type": "ELECTRIC_VAN",
            "max_load_kg": "900.00",
            "current_load_kg": "0.00",
            "gross_weight_tons": "1.80",
            "cargo_capability": "GENERAL",
            "status": "MAINTENANCE",
            "current_node_id": "N14",
            "assigned_driver_id": "D-005",
        }
    ),
    MappingProxyType(
        {
            "vehicle_id": "V-007",
            "plate_no": "新物乡配-07",
            "vehicle_type": "TRICYCLE",
            "max_load_kg": "300.00",
            "current_load_kg": "50.00",
            "gross_weight_tons": "0.80",
            "cargo_capability": "GENERAL",
            "status": "AVAILABLE",
            "current_node_id": "N12",
            "assigned_driver_id": "D-006",
        }
    ),
    MappingProxyType(
        {
            "vehicle_id": "V-008",
            "plate_no": "新物轻卡-08",
            "vehicle_type": "LIGHT_TRUCK",
            "max_load_kg": "2000.00",
            "current_load_kg": "700.00",
            "gross_weight_tons": "4.50",
            "cargo_capability": "GENERAL",
            "status": "AVAILABLE",
            "current_node_id": "N03",
            "assigned_driver_id": "D-007",
        }
    ),
    MappingProxyType(
        {
            "vehicle_id": "V-009",
            "plate_no": "新物冷链-09",
            "vehicle_type": "REFRIGERATED_VAN",
            "max_load_kg": "1600.00",
            "current_load_kg": "500.00",
            "gross_weight_tons": "3.00",
            "cargo_capability": "COLD_CHAIN",
            "status": "IN_TRANSIT",
            "current_node_id": "N11",
            "assigned_driver_id": "D-008",
        }
    ),
    MappingProxyType(
        {
            "vehicle_id": "V-010",
            "plate_no": "新物农运-10",
            "vehicle_type": "LIGHT_TRUCK",
            "max_load_kg": "4000.00",
            "current_load_kg": "1000.00",
            "gross_weight_tons": "6.50",
            "cargo_capability": "FARM_SUPPLY",
            "status": "AVAILABLE",
            "current_node_id": "N01",
            "assigned_driver_id": "D-009",
        }
    ),
    MappingProxyType(
        {
            "vehicle_id": "V-011",
            "plate_no": "新物冷链-11",
            "vehicle_type": "REFRIGERATED_VAN",
            "max_load_kg": "1800.00",
            "current_load_kg": "1300.00",
            "gross_weight_tons": "3.20",
            "cargo_capability": "COLD_CHAIN",
            "status": "AVAILABLE",
            "current_node_id": "N14",
            "assigned_driver_id": None,
        }
    ),
    MappingProxyType(
        {
            "vehicle_id": "V-012",
            "plate_no": "新物电运-12",
            "vehicle_type": "ELECTRIC_VAN",
            "max_load_kg": "1000.00",
            "current_load_kg": "300.00",
            "gross_weight_tons": "2.00",
            "cargo_capability": "GENERAL",
            "status": "AVAILABLE",
            "current_node_id": "N06",
            "assigned_driver_id": "D-010",
        }
    ),
    MappingProxyType(
        {
            "vehicle_id": "V-013",
            "plate_no": "新物厢货-13",
            "vehicle_type": "VAN",
            "max_load_kg": "1200.00",
            "current_load_kg": "260.00",
            "gross_weight_tons": "2.20",
            "cargo_capability": "GENERAL",
            "status": "AVAILABLE",
            "current_node_id": "N07",
            "assigned_driver_id": None,
        }
    ),
    MappingProxyType(
        {
            "vehicle_id": "V-014",
            "plate_no": "新物轻卡-14",
            "vehicle_type": "LIGHT_TRUCK",
            "max_load_kg": "2600.00",
            "current_load_kg": "980.00",
            "gross_weight_tons": "4.80",
            "cargo_capability": "FARM_SUPPLY",
            "status": "IN_TRANSIT",
            "current_node_id": "N08",
            "assigned_driver_id": None,
        }
    ),
    MappingProxyType(
        {
            "vehicle_id": "V-015",
            "plate_no": "新物救援-15",
            "vehicle_type": "VAN",
            "max_load_kg": "1000.00",
            "current_load_kg": "120.00",
            "gross_weight_tons": "2.30",
            "cargo_capability": "GENERAL",
            "status": "AVAILABLE",
            "current_node_id": "N15",
            "assigned_driver_id": None,
        }
    ),
    MappingProxyType(
        {
            "vehicle_id": "V-016",
            "plate_no": "新物电运-16",
            "vehicle_type": "ELECTRIC_VAN",
            "max_load_kg": "900.00",
            "current_load_kg": "0.00",
            "gross_weight_tons": "1.90",
            "cargo_capability": "GENERAL",
            "status": "AVAILABLE",
            "current_node_id": "N10",
            "assigned_driver_id": None,
        }
    ),
    MappingProxyType(
        {
            "vehicle_id": "V-017",
            "plate_no": "新物乡配-17",
            "vehicle_type": "VAN",
            "max_load_kg": "1100.00",
            "current_load_kg": "430.00",
            "gross_weight_tons": "2.10",
            "cargo_capability": "GENERAL",
            "status": "IN_TRANSIT",
            "current_node_id": "N09",
            "assigned_driver_id": None,
        }
    ),
    MappingProxyType(
        {
            "vehicle_id": "V-018",
            "plate_no": "新物检修-18",
            "vehicle_type": "LIGHT_TRUCK",
            "max_load_kg": "2200.00",
            "current_load_kg": "0.00",
            "gross_weight_tons": "4.20",
            "cargo_capability": "GENERAL",
            "status": "MAINTENANCE",
            "current_node_id": "N11",
            "assigned_driver_id": None,
        }
    ),
    MappingProxyType(
        {
            "vehicle_id": "V-019",
            "plate_no": "新物冷链-19",
            "vehicle_type": "REFRIGERATED_VAN",
            "max_load_kg": "1500.00",
            "current_load_kg": "300.00",
            "gross_weight_tons": "2.90",
            "cargo_capability": "COLD_CHAIN",
            "status": "AVAILABLE",
            "current_node_id": "N08",
            "assigned_driver_id": None,
        }
    ),
    MappingProxyType(
        {
            "vehicle_id": "V-020",
            "plate_no": "新物乡配-20",
            "vehicle_type": "VAN",
            "max_load_kg": "1200.00",
            "current_load_kg": "560.00",
            "gross_weight_tons": "2.30",
            "cargo_capability": "GENERAL",
            "status": "IN_TRANSIT",
            "current_node_id": "N08",
            "assigned_driver_id": None,
        }
    ),
)

ORDERS = (
    MappingProxyType(
        {
            "order_no": "DEMO-ORDER-001",
            "cargo_type": "COLD_CHAIN",
            "cargo_weight_kg": "700.00",
            "origin_station_id": "ST-001",
            "destination_station_id": "ST-002",
            "vehicle_id": "V-001",
            "status": "IN_TRANSIT",
        }
    ),
    MappingProxyType(
        {
            "order_no": "DEMO-ORDER-002",
            "cargo_type": "FARM_SUPPLY",
            "cargo_weight_kg": "1200.00",
            "origin_station_id": "ST-001",
            "destination_station_id": "ST-003",
            "vehicle_id": "V-010",
            "status": "PENDING",
        }
    ),
    MappingProxyType(
        {
            "order_no": "DEMO-ORDER-003",
            "cargo_type": "COLD_CHAIN",
            "cargo_weight_kg": "500.00",
            "origin_station_id": "ST-003",
            "destination_station_id": "ST-001",
            "vehicle_id": "V-009",
            "status": "IN_TRANSIT",
        }
    ),
    MappingProxyType(
        {
            "order_no": "DEMO-ORDER-004",
            "cargo_type": "GENERAL",
            "cargo_weight_kg": "300.00",
            "origin_station_id": "ST-001",
            "destination_station_id": "ST-008",
            "vehicle_id": "V-012",
            "status": "PENDING",
        }
    ),
    MappingProxyType(
        {
            "order_no": "DEMO-ORDER-005",
            "cargo_type": "GENERAL",
            "cargo_weight_kg": "850.00",
            "origin_station_id": "ST-001",
            "destination_station_id": "ST-002",
            "vehicle_id": "V-008",
            "status": "IN_TRANSIT",
        }
    ),
    MappingProxyType(
        {
            "order_no": "DEMO-ORDER-006",
            "cargo_type": "COLD_CHAIN",
            "cargo_weight_kg": "450.00",
            "origin_station_id": "ST-006",
            "destination_station_id": "ST-003",
            "vehicle_id": "V-011",
            "status": "PENDING",
        }
    ),
    MappingProxyType(
        {
            "order_no": "DEMO-ORDER-007",
            "cargo_type": "FARM_SUPPLY",
            "cargo_weight_kg": "1600.00",
            "origin_station_id": "ST-004",
            "destination_station_id": "ST-001",
            "vehicle_id": "V-010",
            "status": "PENDING",
        }
    ),
    MappingProxyType(
        {
            "order_no": "DEMO-ORDER-008",
            "cargo_type": "GENERAL",
            "cargo_weight_kg": "260.00",
            "origin_station_id": "ST-008",
            "destination_station_id": "ST-005",
            "vehicle_id": "V-012",
            "status": "PENDING",
        }
    ),
    MappingProxyType(
        {
            "order_no": "DEMO-ORDER-009",
            "cargo_type": "GENERAL",
            "cargo_weight_kg": "900.00",
            "origin_station_id": "ST-001",
            "destination_station_id": "ST-007",
            "vehicle_id": "V-004",
            "status": "IN_TRANSIT",
        }
    ),
    MappingProxyType(
        {
            "order_no": "DEMO-ORDER-010",
            "cargo_type": "COLD_CHAIN",
            "cargo_weight_kg": "600.00",
            "origin_station_id": "ST-003",
            "destination_station_id": "ST-002",
            "vehicle_id": "V-009",
            "status": "PENDING",
        }
    ),
    MappingProxyType(
        {
            "order_no": "DEMO-ORDER-011",
            "cargo_type": "GENERAL",
            "cargo_weight_kg": "400.00",
            "origin_station_id": "ST-001",
            "destination_station_id": "ST-004",
            "vehicle_id": "V-002",
            "status": "PENDING",
        }
    ),
    MappingProxyType(
        {
            "order_no": "DEMO-ORDER-012",
            "cargo_type": "COLD_CHAIN",
            "cargo_weight_kg": "300.00",
            "origin_station_id": "ST-006",
            "destination_station_id": "ST-002",
            "vehicle_id": "V-005",
            "status": "PENDING",
        }
    ),
)

__all__ = ["STATIONS", "ROAD_NODES", "ROAD_EDGES", "DRIVERS", "VEHICLES", "ORDERS"]
