# collector/topology_output.py
# The final collector module — combines all three data sources into
# one clean topology.json file that the graph layer will consume.
#
# WHAT THIS FILE DOES:
# 1. Calls device_info   → gets all devices with their interfaces
# 2. Calls eigrp_reader  → gets all confirmed direct links
# 3. Calls arp_reader    → enriches links with MAC addresses
# 4. Builds a clean JSON structure and writes it to data/topology.json
#
# This is the "handoff" file — everything downstream (graph, API,
# dashboard) reads from this single source of truth.

import sys
sys.stdout.reconfigure(encoding='utf-8')

import json
import os
from datetime import datetime

from collector.device_info  import collect_all_devices
from collector.eigrp_reader import collect_all_eigrp
from collector.arp_reader   import collect_all_arp
from config.settings        import TOPOLOGY_OUTPUT_PATH, TOPOLOGY_PREV_PATH


# ── helpers ───────────────────────────────────────────────────────────────

def _build_device_lookup(devices: list) -> dict:
    """
    Build a dict of {ip: device_id} from device list.
    Used to resolve neighbour IPs to device IDs.
    Example: {"10.0.1.2": "R2", "10.0.2.2": "R3"}
    """
    lookup = {}
    for device in devices:
        # Add the management IP
        lookup[device["ip"]] = device["id"]
        # Also add all interface IPs so we can match EIGRP neighbour IPs
        for iface in device["interfaces"]:
            if iface["ip"]:
                lookup[iface["ip"]] = device["id"]
    return lookup


def _build_mac_lookup(arp_entries: list) -> dict:
    """
    Build a dict of {ip: mac} from ARP entries.
    Used to enrich links with MAC addresses.
    """
    lookup = {}
    for entry in arp_entries:
        if entry["mac"] != "unknown":
            lookup[entry["ip"]] = entry["mac"]
    return lookup


def _build_connections(eigrp_entries: list, ip_to_id: dict, mac_lookup: dict) -> list:
    """
    Convert EIGRP neighbour entries into clean connection objects.

    Each EIGRP entry says "device X has neighbour at IP Y on interface Z".
    We resolve Y to a device ID using ip_to_id lookup.
    We deduplicate — R1→R2 and R2→R1 become one single connection.

    Returns a list of unique connections:
    {
      "from":      "R1",
      "to":        "R2",
      "from_if":   "2",        ← interface index on the 'from' side
      "to_if":     "1",        ← interface index on the 'to' side
      "neighbour_ip": "10.0.1.2",
      "mac":       "ca:01:...",
      "srtt_ms":   "51"
    }
    """
    connections = []
    seen = set()  # tracks pairs we've already added to avoid duplicates

    # Build a reverse lookup: (device, neighbour_id) → if_index
    # So when we process R2→R1, we can find R1's if_index toward R2
    ifindex_map = {}
    for entry in eigrp_entries:
        neighbour_id = ip_to_id.get(entry["neighbour"])
        if neighbour_id:
            ifindex_map[(entry["device"], neighbour_id)] = entry["if_index"]

    for entry in eigrp_entries:
        device_id    = entry["device"]
        neighbour_ip = entry["neighbour"]
        neighbour_id = ip_to_id.get(neighbour_ip)

        if not neighbour_id:
            # Could not resolve neighbour IP to a known device — skip
            print(f"  [WARN] Could not resolve neighbour IP {neighbour_ip} for {device_id}")
            continue

        # Create a canonical pair key — always smaller ID first
        # so R1-R2 and R2-R1 produce the same key
        pair = tuple(sorted([device_id, neighbour_id]))
        if pair in seen:
            continue
        seen.add(pair)

        connections.append({
            "from":         device_id,
            "to":           neighbour_id,
            "from_if":      entry["if_index"],
            "to_if":        ifindex_map.get((neighbour_id, device_id), "unknown"),
            "neighbour_ip": neighbour_ip,
            "mac":          mac_lookup.get(neighbour_ip, "unknown"),
            "srtt_ms":      entry["srtt_ms"]
        })

    return connections


# ── main function ─────────────────────────────────────────────────────────

def build_topology() -> dict:
    """
    Run full topology discovery and return the topology dict.
    """
    print("\n" + "="*55)
    print(" SCADA — Network Topology Discovery")
    print("="*55)

    # Step 1: Collect all data
    devices         = collect_all_devices()
    eigrp_entries   = collect_all_eigrp()
    arp_entries     = collect_all_arp()

    # Step 2: Build lookup tables
    ip_to_id    = _build_device_lookup(devices)
    mac_lookup  = _build_mac_lookup(arp_entries)

    # Step 3: Build connections from EIGRP data
    connections = _build_connections(eigrp_entries, ip_to_id, mac_lookup)

    # Step 4: Assemble final topology
    topology = {
        "timestamp":   datetime.now().isoformat(),
        "device_count": len(devices),
        "link_count":   len(connections),
        "devices":     devices,
        "connections": connections,
        "alerts":      []
    }

    return topology


def save_topology(topology: dict):
    """
    Save topology to data/topology.json.
    Also saves the previous version to data/topology_prev.json
    so the change detector can compare them.
    """
    os.makedirs("data", exist_ok=True)

    # Rotate current → previous before overwriting
    if os.path.exists(TOPOLOGY_OUTPUT_PATH):
        with open(TOPOLOGY_OUTPUT_PATH, "r", encoding="utf-8") as f:
            prev = f.read()
        with open(TOPOLOGY_PREV_PATH, "w", encoding="utf-8") as f:
            f.write(prev)

    # Write new topology
    with open(TOPOLOGY_OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(topology, f, indent=2, ensure_ascii=False)

    print(f"\n✓ Topology saved to {TOPOLOGY_OUTPUT_PATH}")
    print(f"  Devices:     {topology['device_count']}")
    print(f"  Links:       {topology['link_count']}")
    print(f"  Timestamp:   {topology['timestamp']}")


# ── quick test ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    topology = build_topology()
    save_topology(topology)

    print("\n── Connections Found ───────────────────────────────")
    for conn in topology["connections"]:
        print(f"  {conn['from']} ↔ {conn['to']}  "
              f"(srtt: {conn['srtt_ms']}ms, mac: {conn['mac']})")