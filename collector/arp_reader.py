# collector/arp_reader.py
# Module 2 — Reads the ARP table from every device.
#
# WHY ARP TABLES MATTER FOR TOPOLOGY DISCOVERY:
# Every router keeps an ARP table — a list of "IP address → MAC address"
# mappings for every device it has recently communicated with.
# By reading ARP tables, we can discover WHICH devices are directly
# connected to each router, even without CDP/LLDP.
#
# Example: If R2's ARP table contains 10.0.1.1 → MAC of R1,
# we know R2 and R1 are directly connected.

import sys
sys.stdout.reconfigure(encoding='utf-8')

from collector.snmp_client import snmp_walk
from config.settings import DEVICES

# ── OIDs ─────────────────────────────────────────────────────────────────
# ipNetToMediaTable — the standard ARP table in MIB-II
# Each row = one ARP entry (one neighbour the device knows about)

ARP_IP_ADDRESS = "1.3.6.1.2.1.4.22.1.3"  # IP address of the neighbour
ARP_MAC        = "1.3.6.1.2.1.4.22.1.2"  # MAC address of the neighbour
ARP_IF_INDEX   = "1.3.6.1.2.1.4.22.1.1"  # which interface learned this ARP entry


# ── helpers ───────────────────────────────────────────────────────────────

def _bytes_to_mac(raw: str) -> str:
    """
    Convert raw MAC bytes to human-readable format like 'ca:01:09:37:00:00'

    SNMP returns MAC addresses as raw byte strings.
    We encode to latin-1 to get the byte values, then format as hex.
    Example: '\xca\x01\x09\x37\x00\x00' → 'ca:01:09:37:00:00'
    """
    try:
        return ":".join(f"{b:02x}" for b in raw.encode('latin-1'))
    except Exception:
        return raw


# ── main function ─────────────────────────────────────────────────────────

def get_arp_table(device: dict) -> list:
    """
    Read the ARP table of a single device.

    Returns a list of ARP entries, each containing:
    - if_index:   which interface on THIS device learned this entry
    - ip:         IP address of the neighbour
    - mac:        MAC address of the neighbour

    How the OID suffix works for ARP tables:
    The OID suffix is IF_INDEX.IP_ADDRESS
    Example: 1.3.6.1.2.1.4.22.1.3.1.10.0.1.2
                                      ^ ^^^^^^^
                                      |    IP address (10.0.1.2)
                                      interface index (1)
    """
    ip        = device["ip"]
    priv_type = device["priv"]
    dev_id    = device["id"]

    print(f"  Reading ARP table: {dev_id} ({ip})...")

    # Walk the IP address column — OID suffix = if_index.ip_address
    ip_results  = snmp_walk(ip, ARP_IP_ADDRESS, priv_type)
    mac_results = snmp_walk(ip, ARP_MAC,        priv_type)

    # Build MAC lookup: "if_index.ip" → mac
    mac_lookup = {}
    for oid, val in mac_results:
        # Extract the suffix after the base OID
        suffix = ".".join(oid.split(".")[-5:])  # if_index + 4 IP octets
        mac_lookup[suffix] = _bytes_to_mac(val)

    # Build ARP entries
    arp_entries = []
    for oid, val in ip_results:
        parts    = oid.split(".")
        if_index = parts[-5]                          # 5th from end = if_index
        ip_addr  = ".".join(parts[-4:])               # last 4 = IP address
        suffix   = ".".join(parts[-5:])               # if_index + IP

        arp_entries.append({
            "device":   dev_id,
            "if_index": if_index,
            "ip":       ip_addr,
            "mac":      mac_lookup.get(suffix, "unknown")
        })

    return arp_entries


def collect_all_arp() -> list:
    """
    Read ARP tables from every device in settings.py.
    Returns a flat list of all ARP entries across all devices.
    """
    print("Collecting ARP tables from all devices...")
    all_entries = []
    for device in DEVICES:
        try:
            entries = get_arp_table(device)
            all_entries.extend(entries)
            print(f"    → {len(entries)} ARP entries found")
        except Exception as e:
            print(f"  [FAILED] {device['id']}: {e}")
    return all_entries


# ── quick test ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json
    entries = collect_all_arp()
    print("\n── ARP Table Results ───────────────────────────────")
    print(json.dumps(entries, indent=2))
    print(f"\nTotal ARP entries collected: {len(entries)}")