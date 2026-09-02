from unittest.mock import patch

from app.core.config import Settings
from app.graph_memory.driver import build_neo4j_driver


def test_runtime_driver_disables_transaction_retry_beyond_graph_degradation_budget():
    settings = Settings(_env_file=None, graph_memory_backend="neo4j", neo4j_password="test", neo4j_query_timeout_seconds=0.8)

    with patch("app.graph_memory.driver.AsyncGraphDatabase.driver", return_value=object()) as factory:
        driver = build_neo4j_driver(settings)

    assert driver is not None
    assert factory.call_args.kwargs["max_transaction_retry_time"] == 0
