# graph/pipeline.py
# Full pipeline orchestrator — runs collect → analyse → store in one command.
#
# This is the file you run in production.
# It replaces running each module separately.
#
# FLOW:
#   1. Run topology discovery (collector)
#   2. Build NetworkX graph
#   3. Run network analysis
#   4. Save snapshot to database
#   5. Store alerts via alert_engine (with deduplication)
#   6. Schedule and repeat

import sys
sys.stdout.reconfigure(encoding='utf-8')

import schedule
import time
from datetime import datetime

from collector.topology_output  import build_topology, save_topology
from graph.builder              import build_graph
from graph.analyzer             import run_full_analysis
from graph.database             import save_snapshot
from graph.alert_engine         import store_alerts, get_alert_summary
from config.settings            import COLLECTOR_INTERVAL_SECONDS


def run_pipeline(verbose: bool = True):
    """
    One full pipeline cycle:
    collect → graph → analyse → store → alert
    """
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Pipeline starting...")

    # Step 1 — Collect topology from network
    topology = build_topology()
    save_topology(topology)

    # Step 2 — Build graph
    G = build_graph(topology)

    # Step 3 — Analyse (optional verbose output)
    if verbose:
        run_full_analysis(G)

    # Step 4 — Save to database
    save_snapshot(topology)

    # Step 5 — Store alerts with deduplication
    if topology.get("alerts"):
        store_alerts(topology["alerts"])

    # Step 6 — Print health summary
    summary = get_alert_summary()
    print(f"\n── Network Health ──────────────────────────────────")
    print(f"  Status:         {summary['status']}")
    print(f"  Unacked alerts: {summary['unacknowledged']}")
    print(f"  Critical:       {summary['critical']}")
    print(f"  Devices:        {topology['device_count']}")
    print(f"  Links:          {topology['link_count']}")

    return topology, G


def start_pipeline(verbose: bool = False):
    """
    Run pipeline once immediately then on schedule.
    Press Ctrl+C to stop.
    """
    print("="*55)
    print(" GAIL SCADA — Full Pipeline")
    print(f" Interval: every {COLLECTOR_INTERVAL_SECONDS} seconds")
    print(" Press Ctrl+C to stop")
    print("="*55)

    run_pipeline(verbose=True)  # first run always verbose

    schedule.every(COLLECTOR_INTERVAL_SECONDS).seconds.do(
        run_pipeline, verbose=verbose
    )

    while True:
        try:
            schedule.run_pending()
            time.sleep(1)
        except KeyboardInterrupt:
            print("\n\nPipeline stopped.")
            break


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "continuous":
        start_pipeline(verbose=False)
    else:
        run_pipeline(verbose=True)