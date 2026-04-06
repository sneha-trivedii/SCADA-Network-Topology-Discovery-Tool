# collector/eigrp_reader.py
# Module 3 — Reads EIGRP neighbour tables from every router.
#
# WHY EIGRP NEIGHBOURS ARE THE BEST DATA SOURCE:
# ARP tables tell us about recently seen devices, but they can contain
# stale entries. EIGRP neighbour tables are different — a device only
# appears as an EIGRP neighbour if it is RIGHT NOW actively exchanging
# routing updates. This means every EIGRP neighbour = a confirmed,
# live, direct physical connection.
#
# This is the most reliable way to discover topology without CDP/LLDP.
#
# Cisco EIGRP MIB: 1.3.6.1.4.1.9.9.449
# This is a Cisco-proprietary MIB (not standard MIB-II) so it only
# works on Cisco devices — perfect for our GAIL network.

import sys
sys.stdout.reconfigure(encoding='utf-8')

from collector.snmp_client import snmp_walk
from config.settings import DEVICES

# ── OIDs ─────────────────────────────────────────────────────────────────
# All under Cisco EIGRP MIB: 1.3.6.1.4.1.9.9.449.1.4.1

EIGRP_PEER_ADDR    = "1.3.6.1.4.1.9.9.449.1.4.1.1.3"  # neighbour IP address
EIGRP_PEER_IFINDEX = "1.3.6.1.4.1.9.9.449.1.4.1.1.4"  # interface index facing neighbour
EIGRP_PEER_UPTIME  = "1.3.6.1.4.1.9.9.449.1.4.1.1.7"  # how long neighbour has been up
EIGRP_PEER_SRTT    = "1.3.6.1.4.1.9.9.449.1.4.1.1.8"  # smooth round trip time (ms)


# ── helpers ───────────────────────────────────────────────────────────────

def _bytes_to_ip(raw: str) -> str:
    """
    Convert raw 4-byte string to IP address.
    Example: bytes [10, 0, 1, 2] → '10.0.1.2'
    """
    try:
        return ".".join(str(b) for b in raw.encode('latin-1'))
    except Exception:
        return raw


def get_eigrp_neighbours(device: dict) -> list:
    ip        = device["ip"]
    priv_type = device["priv"]
    dev_id    = device["id"]

    print(f"  Reading EIGRP neighbours: {dev_id} ({ip})...")

    peer_results    = snmp_walk(ip, EIGRP_PEER_ADDR,    priv_type)
    ifindex_results = snmp_walk(ip, EIGRP_PEER_IFINDEX, priv_type)
    uptime_results  = snmp_walk(ip, EIGRP_PEER_UPTIME,  priv_type)
    srtt_results    = snmp_walk(ip, EIGRP_PEER_SRTT,    priv_type)

    # Key = last 3 OID parts (e.g. "0.1.0", "0.1.1")
    # This is the unique index for each neighbour entry
    def _build_lookup(results):
        lookup = {}
        for oid, val in results:
            key = ".".join(oid.split(".")[-3:])
            lookup[key] = val
        return lookup

    ifindex_lookup = _build_lookup(ifindex_results)
    uptime_lookup  = _build_lookup(uptime_results)
    srtt_lookup    = _build_lookup(srtt_results)

    neighbours = []
    for oid, val in peer_results:
        key          = ".".join(oid.split(".")[-3:])
        neighbour_ip = _bytes_to_ip(val)  # IP is in the VALUE as raw bytes

        neighbours.append({
            "device":     dev_id,
            "neighbour":  neighbour_ip,
            "if_index":   ifindex_lookup.get(key, "unknown"),
            "uptime":     uptime_lookup.get(key,  "unknown"),
            "srtt_ms":    srtt_lookup.get(key,    "unknown")
        })

    return neighbours


def collect_all_eigrp() -> list:
    """
    Read EIGRP neighbour tables from every device.
    Returns a flat list of all neighbour relationships.

    Note: Each link appears TWICE — once from each end.
    Example: R1→R2 and R2→R1 are both in the list.
    The graph builder will deduplicate these into one edge.
    """
    print("Collecting EIGRP neighbours from all devices...")
    all_neighbours = []
    for device in DEVICES:
        try:
            neighbours = get_eigrp_neighbours(device)
            all_neighbours.extend(neighbours)
            print(f"    → {len(neighbours)} EIGRP neighbours found")
        except Exception as e:
            print(f"  [FAILED] {device['id']}: {e}")
    return all_neighbours


# ── quick test ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json
    neighbours = collect_all_eigrp()
    print("\n── EIGRP Neighbour Results ─────────────────────────")
    print(json.dumps(neighbours, indent=2))
    print(f"\nTotal EIGRP neighbour relationships: {len(neighbours)}")