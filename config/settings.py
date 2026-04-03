# config/settings.py

SNMP_CONFIG = {
    "username": "snmpuser",
    "auth_key": "AuthPass123",
    "priv_key": "PrivPass123",
    "auth_protocol": "SHA",
    "port": 161,
    "timeout": 2,
    "retries": 1
}

# R1/R2/R3 are c7200 — support AES128
# R4-SWL4 are c3745 — DES only
DEVICES = [
    {"id": "R1",    "ip": "192.168.100.1",  "hostname": "R1",    "tier": "core",         "priv": "AES128"},
    {"id": "R2",    "ip": "10.0.1.2",        "hostname": "R2",    "tier": "distribution", "priv": "AES128"},
    {"id": "R3",    "ip": "10.0.2.2",        "hostname": "R3",    "tier": "distribution", "priv": "AES128"},
    {"id": "R4",    "ip": "10.0.4.2",        "hostname": "R4",    "tier": "dist-access",  "priv": "DES"},
    {"id": "R5",    "ip": "10.0.5.2",        "hostname": "R5",    "tier": "dist-access",  "priv": "DES"},
    {"id": "R6",    "ip": "10.0.6.2",        "hostname": "R6",    "tier": "dist-access",  "priv": "DES"},
    {"id": "R7",    "ip": "10.0.7.2",        "hostname": "R7",    "tier": "dist-access",  "priv": "DES"},
    {"id": "SWL1",  "ip": "10.0.11.2",       "hostname": "SWL1",  "tier": "access",       "priv": "DES"},
    {"id": "SWL2",  "ip": "10.0.12.2",       "hostname": "SWL2",  "tier": "access",       "priv": "DES"},
    {"id": "SWL3",  "ip": "10.0.13.2",       "hostname": "SWL3",  "tier": "access",       "priv": "DES"},
    {"id": "SWL4",  "ip": "10.0.14.2",       "hostname": "SWL4",  "tier": "access",       "priv": "DES"},
]

COLLECTOR_INTERVAL_SECONDS = 60

TOPOLOGY_OUTPUT_PATH = "data/topology.json"
TOPOLOGY_PREV_PATH   = "data/topology_prev.json"

DATABASE_URL = "sqlite:///data/topology.db"

JWT_SECRET_KEY = "change-this-in-production"
JWT_ALGORITHM  = "HS256"
JWT_EXPIRY_MINUTES = 60