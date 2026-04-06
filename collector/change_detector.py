# collector/change_detector.py
# Module 4 — Runs topology discovery on a schedule and detects changes.
#
# WHAT THIS MODULE DOES:
# Every 60 seconds (configurable), it runs a full topology discovery.
# It then compares the new topology to the previous one and generates
# typed alerts for any differences found:
#
#   - NEW_DEVICE:     a device appeared that wasn't there before
#   - LOST_DEVICE:    a device disappeared from the topology
#   - NEW_LINK:       a new connection appeared between two devices
#   - LOST_LINK:      an existing connection went down
#   - IP_CHANGED:     a device's IP address changed
#
# WHY THIS MATTERS FOR SCADA SECURITY:
# In a pipeline control network, any unexpected new device is a
# potential security threat — an attacker plugging in a rogue device.
# This module is what makes the tool "secure" and "automatic" as
# required by the SIH problem statement.

import sys
sys.stdout.reconfigure(encoding='utf-8')

import json
import os
import time
import schedule
from datetime import datetime

from collector.topology_output import build_topology, save_topology
from config.settings import (
    TOPOLOGY_OUTPUT_PATH,
    TOPOLOGY_PREV_PATH,
    COLLECTOR_INTERVAL_SECONDS
)


# ── alert builder ─────────────────────────────────────────────────────────

def _make_alert(alert_type: str, message: str, details: dict) -> dict:
    return {
        "type":      alert_type,
        "message":   message,
        "details":   details,
        "timestamp": datetime.now().isoformat()
    }


# ── comparison logic ──────────────────────────────────────────────────────

def compare_topologies(old: dict, new: dict) -> list:
    """
    Compare two topology snapshots and return a list of alerts.

    This is the core logic of the change detector.
    We compare devices and connections between old and new snapshots.
    """
    alerts = []

    # ── Device comparison ─────────────────────────────────────────────────
    old_devices = {d["id"]: d for d in old.get("devices", [])}
    new_devices = {d["id"]: d for d in new.get("devices", [])}

    old_device_ids = set(old_devices.keys())
    new_device_ids = set(new_devices.keys())

    # New devices that weren't in the previous snapshot
    for dev_id in new_device_ids - old_device_ids:
        dev = new_devices[dev_id]
        alerts.append(_make_alert(
            "NEW_DEVICE",
            f"New device detected: {dev_id} ({dev['ip']})",
            {"device_id": dev_id, "ip": dev["ip"], "tier": dev["tier"]}
        ))

    # Devices that disappeared
    for dev_id in old_device_ids - new_device_ids:
        dev = old_devices[dev_id]
        alerts.append(_make_alert(
            "LOST_DEVICE",
            f"Device went offline: {dev_id} ({dev['ip']})",
            {"device_id": dev_id, "ip": dev["ip"]}
        ))

    # IP changes on existing devices
    for dev_id in old_device_ids & new_device_ids:
        old_ip = old_devices[dev_id]["ip"]
        new_ip = new_devices[dev_id]["ip"]
        if old_ip != new_ip:
            alerts.append(_make_alert(
                "IP_CHANGED",
                f"IP changed on {dev_id}: {old_ip} → {new_ip}",
                {"device_id": dev_id, "old_ip": old_ip, "new_ip": new_ip}
            ))

    # ── Link comparison ───────────────────────────────────────────────────
    # Represent each link as a frozenset so R1-R2 == R2-R1
    def link_set(topology):
        return {
            frozenset([c["from"], c["to"]])
            for c in topology.get("connections", [])
        }

    old_links = link_set(old)
    new_links = link_set(new)

    # New links
    for link in new_links - old_links:
        devices = list(link)
        alerts.append(_make_alert(
            "NEW_LINK",
            f"New link detected: {devices[0]} ↔ {devices[1]}",
            {"from": devices[0], "to": devices[1]}
        ))

    # Lost links
    for link in old_links - new_links:
        devices = list(link)
        alerts.append(_make_alert(
            "LOST_LINK",
            f"Link went down: {devices[0]} ↔ {devices[1]}",
            {"from": devices[0], "to": devices[1]}
        ))

    return alerts


def load_json(path: str) -> dict:
    """Load a JSON file, return empty dict if not found."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        return {}


# ── main discovery cycle ──────────────────────────────────────────────────

def run_discovery_cycle():
    """
    One full discovery cycle:
    1. Load previous topology
    2. Collect new topology
    3. Compare and generate alerts
    4. Save new topology with alerts attached
    """
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Starting discovery cycle...")

    # Load previous snapshot before overwriting
    old_topology = load_json(TOPOLOGY_OUTPUT_PATH)

    # Run full discovery
    new_topology = build_topology()

    # Compare
    if old_topology:
        alerts = compare_topologies(old_topology, new_topology)
        new_topology["alerts"] = alerts
        if alerts:
            print(f"\n⚠ {len(alerts)} alert(s) detected:")
            for alert in alerts:
                print(f"  [{alert['type']}] {alert['message']}")
        else:
            print("  ✓ No changes detected")
    else:
        print("  ✓ First run — no previous snapshot to compare")
        new_topology["alerts"] = []

    # Save
    save_topology(new_topology)
    return new_topology


# ── scheduler ─────────────────────────────────────────────────────────────

def start_continuous_monitoring():
    """
    Run discovery once immediately, then on a schedule.
    Press Ctrl+C to stop.
    """
    print("="*55)
    print(" SCADA — Continuous Topology Monitoring")
    print(f" Interval: every {COLLECTOR_INTERVAL_SECONDS} seconds")
    print(" Press Ctrl+C to stop")
    print("="*55)

    # Run immediately on start
    run_discovery_cycle()

    # Then schedule recurring runs
    schedule.every(COLLECTOR_INTERVAL_SECONDS).seconds.do(run_discovery_cycle)

    while True:
        try:
            schedule.run_pending()
            time.sleep(1)
        except KeyboardInterrupt:
            print("\n\nMonitoring stopped.")
            break


# ── quick test ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "continuous":
        # Run: python -m collector.change_detector continuous
        start_continuous_monitoring()
    else:
        # Single run for testing
        result = run_discovery_cycle()
        print(f"\nAlerts generated: {len(result['alerts'])}")

        # Show what a change alert looks like by simulating one
        print("\n── Simulating a change alert ────────────────────────")
        fake_old = {"devices": result["devices"], "connections": result["connections"]}
        fake_new = {
            "devices": result["devices"] + [{
                "id": "ROGUE-1",
                "ip": "10.0.99.1",
                "hostname": "unknown",
                "tier": "unknown",
                "interfaces": []
            }],
            "connections": result["connections"][:-1]  # remove last link
        }
        sim_alerts = compare_topologies(fake_old, fake_new)
        for alert in sim_alerts:
            print(f"  [{alert['type']}] {alert['message']}")