# graph/alert_engine.py
# Alert management layer — stores, retrieves, and manages alerts.
#
# WHY A SEPARATE MODULE FOR ALERTS?
# Alerts need more than just storage — they need:
#   - Severity classification (is this critical or just informational?)
#   - Deduplication (don't raise the same alert 60 times)
#   - Acknowledgement workflow (operator marks alert as seen)
#   - Query functions the API can call directly
#
# This module is the single place all alert logic lives.
# The API never touches the database directly for alerts —
# it always goes through this module.

import sys
sys.stdout.reconfigure(encoding='utf-8')

import json
from datetime import datetime, timedelta
from graph.database import (
    init_db, AlertRecord, Session, get_engine
)


# ── severity classification ───────────────────────────────────────────────

SEVERITY_MAP = {
    "NEW_DEVICE":  "CRITICAL",  # unknown device = potential intruder
    "LOST_DEVICE": "HIGH",      # device offline = outage
    "LOST_LINK":   "HIGH",      # link down = connectivity loss
    "NEW_LINK":    "MEDIUM",    # new link = topology change
    "IP_CHANGED":  "MEDIUM",    # IP change = misconfiguration or attack
}

# Alert types that should never be duplicated within a time window
DEDUP_WINDOW_MINUTES = 10


# ── core functions ────────────────────────────────────────────────────────

def store_alerts(alerts: list):
    """
    Store a list of alerts in the database with deduplication.

    DEDUPLICATION LOGIC:
    If the same alert type + message was already stored within
    the last DEDUP_WINDOW_MINUTES, skip it. This prevents flooding
    the database with identical alerts every 60 seconds.

    Example: If R7 goes down and stays down, we only store
    the LOST_LINK alert once, not once per poll cycle.
    """
    if not alerts:
        return

    engine = init_db()
    stored_count = 0

    with Session(engine) as session:
        for alert in alerts:
            # Check for duplicate within time window
            cutoff = datetime.utcnow() - timedelta(minutes=DEDUP_WINDOW_MINUTES)
            existing = session.query(AlertRecord).filter(
                AlertRecord.alert_type == alert["type"],
                AlertRecord.message    == alert["message"],
                AlertRecord.timestamp  >= cutoff
            ).first()

            if existing:
                continue  # duplicate — skip

            severity = SEVERITY_MAP.get(alert["type"], "LOW")

            record = AlertRecord(
                alert_type = alert["type"],
                message    = alert["message"],
                details    = json.dumps({
                    **alert.get("details", {}),
                    "severity": severity
                }),
                timestamp    = datetime.fromisoformat(alert["timestamp"]),
                acknowledged = False
            )
            session.add(record)
            stored_count += 1

        session.commit()

    if stored_count > 0:
        print(f"  ✓ {stored_count} new alert(s) stored")


def get_alerts(
    limit:        int  = 50,
    only_unacked: bool = False,
    alert_type:   str  = None,
    since_minutes: int = None
) -> list:
    """
    Flexible alert query function used by the API.

    Parameters:
      limit:         max number of alerts to return
      only_unacked:  if True, only return unacknowledged alerts
      alert_type:    filter by type e.g. "NEW_DEVICE"
      since_minutes: only return alerts from last N minutes
    """
    engine = init_db()
    with Session(engine) as session:
        query = session.query(AlertRecord)

        if only_unacked:
            query = query.filter(AlertRecord.acknowledged == False)

        if alert_type:
            query = query.filter(AlertRecord.alert_type == alert_type)

        if since_minutes:
            cutoff = datetime.utcnow() - timedelta(minutes=since_minutes)
            query = query.filter(AlertRecord.timestamp >= cutoff)

        records = query.order_by(AlertRecord.timestamp.desc())\
                       .limit(limit)\
                       .all()

        return [
            {
                "id":           r.id,
                "type":         r.alert_type,
                "severity":     json.loads(r.details).get("severity", "UNKNOWN"),
                "message":      r.message,
                "details":      json.loads(r.details),
                "timestamp":    r.timestamp.isoformat(),
                "acknowledged": r.acknowledged
            }
            for r in records
        ]


def acknowledge_alert(alert_id: int) -> bool:
    """
    Mark an alert as acknowledged by an operator.
    Returns True if found and updated, False if not found.
    """
    engine = init_db()
    with Session(engine) as session:
        record = session.query(AlertRecord)\
                        .filter(AlertRecord.id == alert_id)\
                        .first()
        if not record:
            return False
        record.acknowledged = True
        session.commit()
        return True


def get_alert_summary() -> dict:
    """
    Return a summary of current alert state.
    Used by the dashboard header to show overall network health.
    """
    engine = init_db()
    with Session(engine) as session:
        total       = session.query(AlertRecord).count()
        unacked     = session.query(AlertRecord)\
                             .filter(AlertRecord.acknowledged == False)\
                             .count()
        critical    = session.query(AlertRecord)\
                             .filter(AlertRecord.acknowledged == False)\
                             .all()

        critical_count = sum(
            1 for r in critical
            if json.loads(r.details).get("severity") == "CRITICAL"
        )

        # Overall health status
        if critical_count > 0:
            status = "CRITICAL"
        elif unacked > 0:
            status = "WARNING"
        else:
            status = "HEALTHY"

        return {
            "status":          status,
            "total_alerts":    total,
            "unacknowledged":  unacked,
            "critical":        critical_count,
            "last_checked":    datetime.utcnow().isoformat()
        }


# ── quick test ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Simulate storing some alerts
    test_alerts = [
        {
            "type":      "NEW_DEVICE",
            "message":   "New device detected: ROGUE-1 (10.0.99.1)",
            "details":   {"device_id": "ROGUE-1", "ip": "10.0.99.1"},
            "timestamp": datetime.utcnow().isoformat()
        },
        {
            "type":      "LOST_LINK",
            "message":   "Link went down: R7 ↔ SWL4",
            "details":   {"from": "R7", "to": "SWL4"},
            "timestamp": datetime.utcnow().isoformat()
        }
    ]

    print("Storing test alerts...")
    store_alerts(test_alerts)

    print("\nQuerying all alerts:")
    alerts = get_alerts(limit=10)
    for a in alerts:
        print(f"  [{a['severity']:8s}] [{a['type']:12s}] {a['message']}")

    print("\nNetwork health summary:")
    summary = get_alert_summary()
    for key, val in summary.items():
        print(f"  {key}: {val}")

    print("\nAcknowledging alert ID 1...")
    result = acknowledge_alert(1)
    print(f"  Result: {'success' if result else 'not found'}")

    print("\nUnacknowledged alerts after ack:")
    unacked = get_alerts(only_unacked=True)
    print(f"  Count: {len(unacked)}")