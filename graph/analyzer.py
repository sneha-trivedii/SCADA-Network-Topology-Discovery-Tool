# graph/analyzer.py
# Network analysis using graph algorithms.
#
# THIS IS WHERE CS THEORY MEETS REAL NETWORKING.
# Every algorithm here is something you may have studied in class
# but now you're applying it to a real network topology.
#
# ALGORITHMS USED:
#
# 1. BFS (Breadth First Search)
#    - Visits nodes layer by layer starting from a source
#    - In networking: discovers all devices reachable from core
#    - Time complexity: O(V + E)
#
# 2. Dijkstra's Shortest Path
#    - Finds the lowest-cost path between two nodes
#    - We use srtt_ms as the edge weight (lower = faster link)
#    - Time complexity: O(E log V)
#
# 3. Articulation Points (Cut Vertices)
#    - A node whose removal disconnects the graph
#    - In networking: a single point of failure
#    - If this device goes down, some part of the network
#      becomes unreachable
#
# 4. Bridges (Cut Edges)
#    - An edge whose removal disconnects the graph
#    - In networking: a link with no redundant backup
#    - If this link fails, some devices become isolated
#
# 5. Degree Centrality
#    - Measures how "central" or "important" a node is
#    - Based on how many connections it has relative to total nodes
#    - Helps identify the most critical devices in the network

import sys
sys.stdout.reconfigure(encoding='utf-8')

import networkx as nx
from graph.builder import build_graph_from_file


# ── BFS traversal ─────────────────────────────────────────────────────────

def bfs_from_core(G: nx.Graph, start_node: str = "R1") -> dict:
    """
    Perform BFS starting from the core router.

    Returns a dict showing which layer (hop count) each device
    is at from the core. This reveals the actual network hierarchy
    as seen from the routing perspective.

    Example output:
    {
      "R1":   0,   ← the core itself
      "R2":   1,   ← one hop from core
      "R3":   1,
      "R4":   2,   ← two hops from core
      "SWL1": 3    ← three hops from core
    }

    WHY BFS NOT DFS?
    BFS finds the SHORTEST hop count to each node.
    DFS would find A path but not necessarily the shortest one.
    For network hierarchy discovery, shortest hops is what matters.
    """
    if start_node not in G:
        return {"error": f"{start_node} not in graph"}

    layers = {}  # node → hop count
    visited = set()
    queue = [(start_node, 0)]  # (node, depth)

    while queue:
        node, depth = queue.pop(0)  # pop from FRONT = BFS
        if node in visited:
            continue
        visited.add(node)
        layers[node] = depth

        for neighbour in G.neighbors(node):
            if neighbour not in visited:
                queue.append((neighbour, depth + 1))

    return layers


# ── shortest path ─────────────────────────────────────────────────────────

def shortest_path(G: nx.Graph, source: str, target: str) -> dict:
    """
    Find the shortest path between two devices using Dijkstra's algorithm.
    Uses srtt_ms as edge weight — lower latency = preferred path.

    Returns:
    {
      "path":         ["SWL1", "R4", "R2", "R1", "R3", "R7", "SWL4"],
      "total_srtt":   sum of srtt_ms along the path,
      "hop_count":    number of hops
    }

    HOW DIJKSTRA WORKS:
    It starts at the source and greedily expands to the lowest-cost
    neighbour first, keeping track of the total cost to reach each node.
    It guarantees the optimal (lowest total cost) path.

    In your network, srtt_ms values from EIGRP tell you the actual
    measured round-trip time on each link — a real quality metric.
    """
    if source not in G or target not in G:
        return {"error": "source or target not in graph"}

    try:
        # nx.shortest_path with weight uses Dijkstra automatically
        path = nx.shortest_path(G, source, target, weight="srtt_ms")

        # Calculate total latency along the path
        total_srtt = 0
        for i in range(len(path) - 1):
            edge = G[path[i]][path[i+1]]
            try:
                total_srtt += int(edge.get("srtt_ms", 0))
            except (ValueError, TypeError):
                pass

        return {
            "source":     source,
            "target":     target,
            "path":       path,
            "hop_count":  len(path) - 1,
            "total_srtt": total_srtt
        }
    except nx.NetworkXNoPath:
        return {"error": f"No path between {source} and {target}"}


# ── redundancy analysis ───────────────────────────────────────────────────

def find_articulation_points(G: nx.Graph) -> list:
    """
    Find all articulation points (single points of failure).

    An articulation point is a node that, if removed, would split
    the graph into two or more disconnected components.

    WHY THIS MATTERS FOR SCADA:
    If a pipeline control network has articulation points, those
    devices are critical — their failure would isolate field stations
    from the control centre, potentially causing dangerous situations.

    NetworkX uses Tarjan's algorithm internally to find these.
    Time complexity: O(V + E)
    """
    points = list(nx.articulation_points(G))
    result = []
    for node in points:
        tier = G.nodes[node].get("tier", "unknown")
        ip   = G.nodes[node].get("ip", "")
        result.append({
            "device": node,
            "tier":   tier,
            "ip":     ip,
            "risk":   "HIGH" if tier == "core" else "MEDIUM"
        })
    return result


def find_bridges(G: nx.Graph) -> list:
    """
    Find all bridges (links with no redundant backup).

    A bridge is an edge that, if removed, would disconnect the graph.
    In your network, links to SWL devices are bridges — if R4↔SWL1
    goes down, SWL1 is completely isolated with no backup path.

    This directly tells you where to add redundant links in a
    real network to improve resilience.
    """
    bridge_edges = list(nx.bridges(G))
    result = []
    for u, v in bridge_edges:
        edge = G[u][v]
        result.append({
            "from":    u,
            "to":      v,
            "srtt_ms": edge.get("srtt_ms", "unknown"),
            "risk":    "HIGH"
        })
    return result


# ── centrality ────────────────────────────────────────────────────────────

def degree_centrality(G: nx.Graph) -> list:
    """
    Calculate degree centrality for every node.

    Degree centrality = node_degree / (total_nodes - 1)
    It ranges from 0 to 1.
    A node with centrality 1.0 would be connected to every other node.

    This tells you which devices are most "important" to the network
    from a connectivity perspective — losing a high-centrality device
    has more impact than losing a low-centrality one.
    """
    centrality = nx.degree_centrality(G)
    result = []
    for node, score in sorted(centrality.items(),
                               key=lambda x: x[1], reverse=True):
        result.append({
            "device":      node,
            "centrality":  round(score, 4),
            "tier":        G.nodes[node].get("tier", "unknown"),
            "ip":          G.nodes[node].get("ip", "")
        })
    return result


# ── full analysis report ──────────────────────────────────────────────────

def run_full_analysis(G: nx.Graph):
    """Run all analyses and print a complete network health report."""

    print("\n" + "="*55)
    print(" Network — Graph Analysis Report")
    print("="*55)

    # BFS layers
    print("\n── BFS from Core (R1) — Network Layers ────────────")
    layers = bfs_from_core(G, "R1")
    for node, depth in sorted(layers.items(), key=lambda x: x[1]):
        tier = G.nodes[node].get("tier", "")
        bar  = "  " * depth + "└─ "
        print(f"  {bar}{node:8s} (layer {depth}, {tier})")

    # Shortest paths
    print("\n── Shortest Paths (by latency) ─────────────────────")
    test_pairs = [
        ("SWL1", "SWL4"),
        ("SWL2", "SWL3"),
        ("R1",   "SWL4"),
    ]
    for src, dst in test_pairs:
        result = shortest_path(G, src, dst)
        if "error" not in result:
            path_str = " → ".join(result["path"])
            print(f"  {src} to {dst}:")
            print(f"    Path:  {path_str}")
            print(f"    Hops:  {result['hop_count']}")
            print(f"    srtt:  {result['total_srtt']}ms total")

    # Articulation points
    print("\n── Single Points of Failure (Articulation Points) ──")
    points = find_articulation_points(G)
    if points:
        for p in points:
            print(f"  ⚠ {p['device']:8s} tier={p['tier']:15s} risk={p['risk']}")
    else:
        print("  ✓ No articulation points — fully redundant network")

    # Bridges
    print("\n── Links With No Backup (Bridges) ──────────────────")
    bridges = find_bridges(G)
    if bridges:
        for b in bridges:
            print(f"  ⚠ {b['from']} ↔ {b['to']:8s} srtt={b['srtt_ms']}ms  risk={b['risk']}")
    else:
        print("  ✓ No bridges — all links have redundant paths")

    # Centrality
    print("\n── Device Centrality (most important devices) ──────")
    for item in degree_centrality(G):
        bar = "█" * int(item["centrality"] * 20)
        print(f"  {item['device']:8s} {bar:20s} {item['centrality']:.4f}  ({item['tier']})")


# ── quick test ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    G = build_graph_from_file()
    run_full_analysis(G)