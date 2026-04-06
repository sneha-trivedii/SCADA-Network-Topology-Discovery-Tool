# collector/device_info.py
# Module 1 — Collects basic information from every device:
# hostname, description, and all interfaces with their status and IP addresses.
import sys
sys.stdout.reconfigure(encoding='utf-8')
from collector.snmp_client import snmp_get, snmp_walk
from config.settings import DEVICES

# ── OIDs ─────────────────────────────────────────────────────────────────
# These are standard MIB-II OIDs that work on any vendor's device.

SYS_NAME        = "1.3.6.1.2.1.1.5.0"   # hostname
SYS_DESCR       = "1.3.6.1.2.1.1.1.0"   # hardware/software description
IF_DESCR        = "1.3.6.1.2.1.2.2.1.2" # interface names  (walk)
IF_OPER_STATUS  = "1.3.6.1.2.1.2.2.1.8" # interface status (walk): 1=up, 2=down
IF_INDEX_IP     = "1.3.6.1.2.1.4.20.1.2" # maps IP → interface index (walk)
IF_IP_ADDRESS   = "1.3.6.1.2.1.4.20.1.1" # all IP addresses on device   (walk)
IF_SUBNET_MASK  = "1.3.6.1.2.1.4.20.1.3" # subnet masks for each IP     (walk)


# ── helpers ───────────────────────────────────────────────────────────────

def _get_interface_names(ip, priv_type):
    """
    Returns a dict of {if_index: if_name}
    Example: {"1": "FastEthernet0/0", "2": "GigabitEthernet1/0"}
    """
    results = snmp_walk(ip, IF_DESCR, priv_type)
    names = {}
    for oid, val in results:
        # The last number in the OID is the interface index
        index = oid.split(".")[-1]
        names[index] = val
    return names


def _get_interface_statuses(ip, priv_type):
    """
    Returns a dict of {if_index: "up"/"down"}
    """
    results = snmp_walk(ip, IF_OPER_STATUS, priv_type)
    statuses = {}
    for oid, val in results:
        index = oid.split(".")[-1]
        statuses[index] = "up" if val == "1" else "down"
    return statuses

def _bytes_to_mask(raw: str) -> str:
    """Convert raw mask string like '\xff\xff\xff\xfc' to '255.255.255.252'"""
    try:
        return ".".join(str(b) for b in raw.encode('latin-1'))
    except Exception:
        return raw

def _get_ip_assignments(ip, priv_type):
    """
    Returns a dict of {if_index: {"ip": "x.x.x.x", "mask": "x.x.x.x"}}

    How this works:
    - IF_INDEX_IP table maps each IP address to its interface index
      OID suffix IS the IP address, value IS the interface index
    - IF_SUBNET_MASK table maps each IP address to its subnet mask
      OID suffix IS the IP address, value IS the mask
    """
    # Step 1: get IP → interface index mapping
    index_results = snmp_walk(ip, IF_INDEX_IP, priv_type)
    ip_to_index = {}
    for oid, val in index_results:
        # OID looks like 1.3.6.1.2.1.4.20.1.2.10.0.1.1
        # Last 4 numbers are the IP address
        ip_addr = ".".join(oid.split(".")[-4:])
        ip_to_index[ip_addr] = val  # val is the interface index

    # Step 2: get IP → subnet mask mapping
    mask_results = snmp_walk(ip, IF_SUBNET_MASK, priv_type)
    ip_to_mask = {}
    for oid, val in mask_results:
        ip_addr = ".".join(oid.split(".")[-4:])
        ip_to_mask[ip_addr] = val

    # Step 3: combine — build {if_index: {ip, mask}}
    assignments = {}
    for ip_addr, if_index in ip_to_index.items():
        assignments[if_index] = {
            "ip":   ip_addr,
            "mask": _bytes_to_mask(ip_to_mask.get(ip_addr, ""))
        }
    return assignments


# ── main function ─────────────────────────────────────────────────────────

def get_device_info(device: dict) -> dict:
    """
    Query a single device and return all its info as a dictionary.

    Input:  device dict from settings.py
    Output: structured dict with hostname, interfaces, IPs
    """
    ip        = device["ip"]
    priv_type = device["priv"]
    dev_id    = device["id"]

    print(f"  Querying {dev_id} ({ip})...")

    # Basic info
    hostname = snmp_get(ip, SYS_NAME,  priv_type) or dev_id
    descr    = snmp_get(ip, SYS_DESCR, priv_type) or "unknown"

    # Interface tables
    names      = _get_interface_names(ip, priv_type)
    statuses   = _get_interface_statuses(ip, priv_type)
    ip_assigns = _get_ip_assignments(ip, priv_type)

    # Build interface list by combining all three tables
    interfaces = []
    for idx, name in names.items():
        interfaces.append({
            "index":  idx,
            "name":   name,
            "status": statuses.get(idx, "unknown"),
            "ip":     ip_assigns.get(idx, {}).get("ip",   None),
            "mask":   ip_assigns.get(idx, {}).get("mask", None)
        })

    return {
        "id":          dev_id,
        "ip":          ip,
        "hostname":    hostname.split(".")[0],  # strip .localdomain
        "description": descr[:60],              # first 60 chars is enough
        "tier":        device["tier"],
        "interfaces":  interfaces
    }


def collect_all_devices() -> list:
    """
    Query every device in settings.py and return a list of device dicts.
    This is what topology_output.py will call.
    """
    print("Collecting device info from all devices...")
    all_devices = []
    for device in DEVICES:
        try:
            info = get_device_info(device)
            all_devices.append(info)
        except Exception as e:
            print(f"  [FAILED] {device['id']} ({device['ip']}): {e}")
    return all_devices


# ── quick test ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json
    devices = collect_all_devices()
    print("\n── Result ──────────────────────────────")
    print(json.dumps(devices, indent=2))