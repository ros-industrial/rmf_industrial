from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import networkx as nx
from vda5050_core.types import Order


def build_graph(layout: dict) -> tuple[nx.DiGraph, dict]:
    g = nx.DiGraph()
    node_map = {n["nodeId"]: n for n in layout.get("nodes", [])}
    for node_id in node_map:
        g.add_node(node_id)
    for edge in layout.get("edges", []):
        g.add_edge(edge["startNodeId"], edge["endNodeId"], edge_data=edge)
    return g, node_map


def build_order(
    manufacturer: str,
    serial_number: str,
    path_nodes: list[str],
    graph: nx.DiGraph,
    node_map: dict,
    map_id: str,
    allowed_deviation_xy: float | None = None,
    allowed_deviation_theta: float | None = None,
) -> Order:
    vda_nodes = []
    for seq, node_id in enumerate(path_nodes):
        pos = node_map[node_id].get("nodePosition", {})
        vda_nodes.append({
            "nodeId": node_id,
            "sequenceId": seq * 2,
            "released": True,
            "nodePosition": {
                "x": pos.get("x", 0.0),
                "y": pos.get("y", 0.0),
                "mapId": map_id,
                "allowedDeviationXY": allowed_deviation_xy
                    if allowed_deviation_xy is not None
                    else pos.get("allowedDeviationXY", 0.0),
                "allowedDeviationTheta": allowed_deviation_theta
                    if allowed_deviation_theta is not None
                    else pos.get("allowedDeviationTheta", 0.0),
            },
            "actions": [],
        })
    vda_edges = []
    for i in range(len(path_nodes) - 1):
        src, dst = path_nodes[i], path_nodes[i + 1]
        edge_data = graph[src][dst]["edge_data"]
        vda_edges.append({
            "edgeId": edge_data["edgeId"],
            "sequenceId": i * 2 + 1,
            "startNodeId": src,
            "endNodeId": dst,
            "released": True,
            "actions": [],
        })
    return Order.from_json({
        "headerId": 0,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "2.0.0",
        "manufacturer": manufacturer,
        "serialNumber": serial_number,
        "orderId": str(uuid4()),
        "orderUpdateId": 0,
        "nodes": vda_nodes,
        "edges": vda_edges,
    })
