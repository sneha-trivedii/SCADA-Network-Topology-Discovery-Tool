# GAIL SCADA Network Topology Discovery Tool

> Automated network topology discovery, change detection, and visualisation for industrial SCADA environments — built for Smart India Hackathon.

![Dashboard Preview](docs/screenshots/dashboard.png)

---

## Overview

This tool continuously discovers and maps a live SCADA network using SNMPv3 polling, builds a graph model of devices and links, detects topology changes in real time, and serves everything through a secure REST API to an interactive D3.js dashboard.

Built against a GNS3-simulated GAIL pipeline network: 11 devices across 4 tiers, 13 links, EIGRP routing, SNMPv3 with SHA + AES128/DES authentication.

---

## Architecture

```
GNS3 Virtual Network (11 devices · EIGRP AS1 · SNMPv3)
        │  SNMP polls (pysnmp 4.4.12)
        ▼
┌─────────────────────────────────────────┐
│  collector/                             │
│  snmp_client · device_info · arp_reader │
│  eigrp_reader · change_detector         │
│  topology_output                        │
└──────────────┬──────────────────────────┘
               │
        ┌──────▼──────┐      ┌─────────────────┐
        │  SQLite DB  │      │  topology.json  │
        │ topology.db │      │  (live snapshot)│
        └──────┬──────┘      └────────┬────────┘
               └──────────┬───────────┘
                           │
               ┌───────────▼───────────┐
               │  FastAPI  (port 8000) │
               │  JWT auth · REST API  │
               └───────────┬───────────┘
                           │
        ┌──────────────────▼──────────────────┐
        │  Dashboard (D3.js v7)               │
        │  Hierarchical force graph · Alerts  │
        └─────────────────────────────────────┘
```

---

## GNS3 Topology

| Device | Role | Type | IP |
|--------|------|------|----|
| R1 | Core router | c7200 | 192.168.235.136 |
| R2, R3 | Distribution | c7200 | 10.0.x.x |
| R4–R7 | Dist-Access | c3745 | 10.0.x.x |
| SWL1–SWL4 | Access | c3745 | 10.0.x.x |

- **Routing:** EIGRP AS1
- **SNMP:** v3, SHA + AES128 (c7200) / DES (c3745)
- **Host:** Laptop VMnet1 = 192.168.235.1
- **Static route:** `10.0.0.0/16 via 192.168.235.136`

![GNS3 Topology](docs/screenshots/gns3_topology.png)

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Network simulation | GNS3, Cisco IOS (c7200, c3745) |
| SNMP polling | pysnmp 4.4.12 |
| Graph analysis | NetworkX (BFS, Dijkstra, articulation points, betweenness centrality) |
| Storage | SQLAlchemy + SQLite |
| API | FastAPI + JWT auth |
| Frontend | D3.js v7, vanilla JS, industrial dark theme |

---

## Project Structure

```
├── config/
│   └── settings.py          # All device IPs, SNMPv3 credentials
├── collector/
│   ├── snmp_client.py        # SNMPv3 GET/WALK wrapper
│   ├── device_info.py        # sysName, sysDescr, ifTable
│   ├── arp_reader.py         # ARP table → neighbour discovery
│   ├── eigrp_reader.py       # EIGRP neighbour + topology table
│   ├── change_detector.py    # Diff engine, rogue device detection
│   └── topology_output.py   # Write topology.json
├── graph/
│   ├── builder.py            # NetworkX graph construction
│   ├── analyzer.py           # BFS, Dijkstra, centrality, bridges
│   ├── database.py           # SQLAlchemy models + SQLite writes
│   ├── alert_engine.py       # Generate alerts from change diffs
│   └── pipeline.py           # Orchestration: collect → build → store → alert
├── api/
│   └── main.py               # FastAPI app, JWT, all endpoints
├── dashboard/
│   ├── login.html
│   └── index.html            # D3.js force graph dashboard
└── data/
    ├── topology.json         # Live snapshot (written by pipeline)
    └── topology.db           # SQLite database
```

---

## Setup & Run

### Prerequisites

```bash
pip install fastapi uvicorn pysnmp==4.4.12 networkx sqlalchemy python-jose
```

### 1. Configure devices

Edit `config/settings.py` — set device IPs and SNMPv3 credentials for your GNS3 topology.

### 2. Run the discovery pipeline

```bash
python -m graph.pipeline
```

Polls all devices, builds the graph, writes `topology.json` and `topology.db`, fires alerts on changes.

### 3. Start the API server

```bash
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

### 4. Open the dashboard

Navigate to `dashboard/login.html` in a browser.

**Default credentials:** `admin` / `gail2024`

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/auth/token` | Get JWT token |
| GET | `/topology` | Full topology (nodes + links) |
| GET | `/graph/stats` | Centrality, articulation points, bridges |
| GET | `/alerts` | Active change alerts |
| GET | `/devices` | All discovered devices |

All endpoints require `Authorization: Bearer <token>`.

Interactive docs: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## Dashboard Features

- **Hierarchical D3 force graph** — nodes fixed to tier Y positions (Core → Distribution → Dist-Access → Access)
- **Click node** — highlights connected links, dims unrelated nodes
- **Live alert polling** — checks `/alerts` every 5 seconds, shows amber banner on new events
- **Industrial dark theme** — amber/teal colour scheme

![Dashboard Graph](docs/screenshots/graph_view.png)

---

## Alert Demo

### Scenario A — Device goes down

```
# In GNS3, on R7 console:
R7(config)# interface f0/0
R7(config-if)# shutdown
```

Re-run `python -m graph.pipeline` → change_detector fires → alert appears in dashboard.

### Scenario B — Rogue device detected

Add a new host in GNS3 with an IP in `10.0.0.0/16` but credentials not in `settings.py`. The ARP reader picks it up from R1's ARP table → not in known device list → rogue device alert.

![Alert Demo](docs/screenshots/alert_demo.png)

---

## Security

- **SNMPv3** with SHA authentication + AES128 encryption (c7200) / DES (c3745)
- **JWT** bearer token authentication on all API endpoints
- **Rogue device detection** — any MAC/IP not in the known device registry triggers an alert
- No credentials stored in the frontend

---

## Acknowledgements

Built solo for **Smart India Hackathon**, simulating the operational network topology of GAIL (Gas Authority of India Limited) pipeline infrastructure.

---

## License

MIT