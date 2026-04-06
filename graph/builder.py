# graph/builder.py
# Phase 2 entry point — loads topology.json into a NetworkX graph.
#
# GRAPH THEORY BASICS (read this before the code):
#
# A graph G = (V, E) where:
#   V = set of vertices (nodes) — your network devices
#   E = set of edges          — your network links
#
# NetworkX represents this as a Python object where you can:
#   - Add nodes with attributes:  G.add_node("R1", tier="core", ip="...")
#   - Add edges with attributes:  G.add_edge("R1", "R2", srtt=51)
#   - Query neighbours:           G.neighbors("R1") → [R2, R3]
#   - Run algorithms:             nx.shortest_path(G, "SWL1", "SWL4")
#
# We use an UNDIRECTED graph (nx.Graph) because network links work
# both ways — if R1 can reach R2, R2 can reach R1.
# A DIRECTED graph (nx.DiGraph) would be used if links were one-way.

import sys
sys.stdout.reconfigure(encoding='utf-8')

import json
import os
import networkx as nx
from config.settings import TOPOLOGY_OUTPUT_PATH


# ── core builder ──────────────────────────────────────────────────────────

def build_graph(topology: dict) -> nx.Graph:
    """
    Convert a topology dict (from topology.json) into a NetworkX graph.

    Each device becomes a node with these attributes:
      - hostname, ip, tier, description, interfaces

    Each connection becomes an edge with these attributes:
      - from_if, to_if, srtt_ms, mac, neighbour_ip

    Returns a NetworkX Graph object.
    """
    G = nx.Graph()  # undirected graph

    # ── Add nodes ─────────────────────────────────────────────────────────
    # Every device in topology becomes a node.
    # Node ID = device's "id" field (e.g. "R1", "SWL2")
    # Node attributes = everything else about the device

    for device in topology.get("devices", []):
        G.add_node(
            device["id"],
            hostname    = device.get("hostname", device["id"]),
            ip          = device.get("ip", ""),
            tier        = device.get("tier", "unknown"),
            description = device.get("description", ""),
            interfaces  = device.get("interfaces", [])
        )

    # ── Add edges ─────────────────────────────────────────────────────────
    # Every connection in topology becomes an edge.
    # Edge is identified by the two node IDs it connects.
    # Edge attributes = interface indices, latency, MAC

    for conn in topology.get("connections", []):
        G.add_edge(
            conn["from"],
            conn["to"],
            from_if      = conn.get("from_if", ""),
            to_if        = conn.get("to_if", ""),
            srtt_ms      = conn.get("srtt_ms", 0),
            mac          = conn.get("mac", ""),
            neighbour_ip = conn.get("neighbour_ip", "")
        )

    return G


def load_topology_from_file(path: str = None) -> dict:
    """Load topology.json from disk."""
    path = path or TOPOLOGY_OUTPUT_PATH
    if not os.path.exists(path):
        raise FileNotFoundError(f"topology.json not found at {path}. "
                                 f"Run collector first.")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_graph_from_file(path: str = None) -> nx.Graph:
    """Convenience function — load file and build graph in one call."""
    topology = load_topology_from_file(path)
    return build_graph(topology)


# ── graph summary ─────────────────────────────────────────────────────────

def print_graph_summary(G: nx.Graph):
    """
    Print a human-readable summary of the graph.

    KEY GRAPH CONCEPTS explained here:
    - Degree of a node = number of edges connected to it
      R1 has degree 2 (connected to R2 and R3)
      R2 has degree 4 (connected to R1, R3, R4, R5)

    - A connected graph = every node can reach every other node
      This is critical for a network — if False, some devices
      are isolated and unreachable.

    - Density = actual edges / maximum possible edges
      A fully connected graph (every node linked to every other)
      has density 1.0. Your sparse network will be much lower.
    """
    print("\n── Graph Summary ───────────────────────────────────")
    print(f"  Nodes (devices): {G.number_of_nodes()}")
    print(f"  Edges (links):   {G.number_of_edges()}")
    print(f"  Connected:       {nx.is_connected(G)}")
    print(f"  Density:         {nx.density(G):.4f}")

    print("\n── Node Degrees (connections per device) ───────────")
    # Sort by degree descending — most connected devices first
    degrees = sorted(G.degree(), key=lambda x: x[1], reverse=True)
    for node, degree in degrees:
        tier = G.nodes[node].get("tier", "")
        ip   = G.nodes[node].get("ip", "")
        print(f"  {node:8s} degree={degree}  tier={tier:15s} ip={ip}")

    print("\n── Adjacency (who is connected to whom) ────────────")
    for node in G.nodes():
        neighbours = list(G.neighbors(node))
        print(f"  {node:8s} → {neighbours}")


# ── quick test ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Loading topology.json and building graph...")
    G = build_graph_from_file()
    print_graph_summary(G)

    # Show edge attributes for one link as example
    print("\n── Sample Edge Data (R1 ↔ R2) ──────────────────────")
    if G.has_edge("R1", "R2"):
        edge_data = G["R1"]["R2"]
        for key, val in edge_data.items():
            print(f"  {key}: {val}")
    else:
        print("  R1-R2 edge not found")