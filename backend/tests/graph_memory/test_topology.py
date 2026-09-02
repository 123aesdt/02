from app.graph.builder import build_graph


def test_eight_agent_topology_places_graph_memory_after_entity_memory():
    graph = build_graph().get_graph()
    edges = {(edge.source, edge.target) for edge in graph.edges}

    assert edges == {
        ("__start__", "intake"),
        ("intake", "entity_memory"),
        ("entity_memory", "graph_memory"),
        ("graph_memory", "environment"),
        ("environment", "capacity"),
        ("capacity", "routing"),
        ("routing", "dispatch"),
        ("dispatch", "audit"),
        ("audit", "__end__"),
    }
    assert len({node for edge in edges for node in edge} - {"__start__", "__end__"}) == 8

