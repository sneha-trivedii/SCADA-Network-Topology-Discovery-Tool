# api/main.py
# FastAPI backend — serves topology data, alerts, and auth via REST API.
#
# WHAT IS A REST API?
# REST (Representational State Transfer) is a way for programs to
# communicate over HTTP. Your dashboard will send HTTP requests to
# these endpoints and get JSON back.
#
# Example:
#   Browser asks:  GET /api/topology
#   FastAPI says:  {"devices": [...], "connections": [...]}
#
# WHAT IS FastAPI?
# FastAPI is a modern Python web framework. You define functions
# and decorate them with @app.get("/path") or @app.post("/path").
# FastAPI automatically handles HTTP, JSON serialization, and
# generates interactive documentation at /docs.
#
# ENDPOINTS WE'RE BUILDING:
#   POST /auth/login          → get JWT token
#   GET  /api/topology        → full topology (devices + connections)
#   GET  /api/devices         → just devices
#   GET  /api/connections     → just connections
#   GET  /api/alerts          → alerts with filters
#   POST /api/alerts/{id}/ack → acknowledge an alert
#   GET  /api/analysis        → graph analysis results
#   GET  /api/health          → network health summary

import sys
sys.stdout.reconfigure(encoding='utf-8')

import json
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from graph.database     import get_latest_devices, get_latest_connections, init_db
from graph.alert_engine import get_alerts, acknowledge_alert, get_alert_summary
from graph.builder      import build_graph_from_file
from graph.analyzer     import (
    bfs_from_core, find_articulation_points,
    find_bridges, degree_centrality, shortest_path
)
from config.settings import JWT_SECRET_KEY, JWT_ALGORITHM, JWT_EXPIRY_MINUTES


# ── App Setup ─────────────────────────────────────────────────────────────

app = FastAPI(
    title="GAIL SCADA Topology API",
    description="Secure network topology discovery for pipeline networks",
    version="1.0.0"
)

# CORS — allows the dashboard (running in browser) to call this API
# Without this, browsers block cross-origin requests for security
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # in production, restrict to your domain
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files — serves dashboard/index.html and assets
app.mount("/static", StaticFiles(directory="dashboard/static"), name="static")


# ── Authentication ────────────────────────────────────────────────────────
#
# HOW JWT AUTHENTICATION WORKS:
# 1. User sends username + password to POST /auth/login
# 2. Server verifies credentials and returns a JWT token
# 3. User includes token in every future request header:
#    Authorization: Bearer <token>
# 4. Server verifies token on every protected endpoint
#
# JWT (JSON Web Token) is a signed string containing user info.
# It's signed with a secret key so it can't be faked.
# It has an expiry time so stolen tokens eventually become invalid.

pwd_context    = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme  = OAuth2PasswordBearer(tokenUrl="auth/login")

# In production these would come from a database
# For now, one hardcoded operator account
USERS = {
    "admin": {
        "username": "admin",
        "hashed_password": pwd_context.hash("gail2024"),
        "role": "operator"
    }
}


class Token(BaseModel):
    access_token: str
    token_type:   str


def create_token(username: str) -> str:
    """Create a JWT token for a user."""
    expire = datetime.utcnow() + timedelta(minutes=JWT_EXPIRY_MINUTES)
    payload = {"sub": username, "exp": expire}
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme)) -> str:
    """
    Dependency — verifies JWT token on every protected endpoint.
    FastAPI calls this automatically when you add it to a route.
    If token is invalid or expired, returns 401 Unauthorized.
    """
    try:
        payload  = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        username = payload.get("sub")
        if not username or username not in USERS:
            raise HTTPException(status_code=401, detail="Invalid token")
        return username
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


# ── Auth Endpoints ────────────────────────────────────────────────────────

@app.post("/auth/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Login endpoint — returns JWT token if credentials are valid.
    The OAuth2PasswordRequestForm automatically reads username
    and password from the request body.
    """
    user = USERS.get(form_data.username)
    if not user or not pwd_context.verify(form_data.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )
    token = create_token(form_data.username)
    return {"access_token": token, "token_type": "bearer"}


# ── Topology Endpoints ────────────────────────────────────────────────────

@app.get("/api/topology")
def get_topology(username: str = Depends(get_current_user)):
    """
    Return complete topology — devices and connections.
    Protected: requires valid JWT token.
    """
    devices     = get_latest_devices()
    connections = get_latest_connections()
    if not devices:
        raise HTTPException(status_code=404, detail="No topology data found. Run pipeline first.")
    return {
        "devices":     devices,
        "connections": connections,
        "timestamp":   datetime.utcnow().isoformat()
    }


@app.get("/api/devices")
def get_devices(username: str = Depends(get_current_user)):
    """Return just the device list."""
    devices = get_latest_devices()
    return {"devices": devices, "count": len(devices)}


@app.get("/api/connections")
def get_connections(username: str = Depends(get_current_user)):
    """Return just the connection list."""
    connections = get_latest_connections()
    return {"connections": connections, "count": len(connections)}


# ── Alert Endpoints ───────────────────────────────────────────────────────

@app.get("/api/alerts")
def get_alerts_endpoint(
    limit:         int           = 50,
    only_unacked:  bool          = False,
    alert_type:    Optional[str] = None,
    since_minutes: Optional[int] = None,
    username:      str           = Depends(get_current_user)
):
    """
    Return alerts with optional filters.
    Query params: ?limit=20&only_unacked=true&alert_type=NEW_DEVICE
    """
    alerts = get_alerts(
        limit=limit,
        only_unacked=only_unacked,
        alert_type=alert_type,
        since_minutes=since_minutes
    )
    return {"alerts": alerts, "count": len(alerts)}


@app.post("/api/alerts/{alert_id}/ack")
def ack_alert(alert_id: int, username: str = Depends(get_current_user)):
    """Acknowledge a specific alert by ID."""
    success = acknowledge_alert(alert_id)
    if not success:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"message": f"Alert {alert_id} acknowledged", "acknowledged_by": username}


# ── Analysis Endpoints ────────────────────────────────────────────────────

@app.get("/api/analysis")
def get_analysis(username: str = Depends(get_current_user)):
    """
    Run graph analysis and return results.
    Called by dashboard to show articulation points, bridges, centrality.
    """
    try:
        G = build_graph_from_file()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="No topology data found. Run pipeline first.")

    return {
        "articulation_points": find_articulation_points(G),
        "bridges":             find_bridges(G),
        "centrality":          degree_centrality(G),
        "bfs_layers":          bfs_from_core(G, "R1"),
        "timestamp":           datetime.utcnow().isoformat()
    }


@app.get("/api/path")
def get_path(
    source:   str,
    target:   str,
    username: str = Depends(get_current_user)
):
    """
    Find shortest path between two devices.
    Usage: GET /api/path?source=SWL1&target=SWL4
    """
    try:
        G = build_graph_from_file()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="No topology data found.")
    result = shortest_path(G, source, target)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


# ── Health Endpoint ───────────────────────────────────────────────────────

@app.get("/api/health")
def get_health(username: str = Depends(get_current_user)):
    """Network health summary — used by dashboard header."""
    return get_alert_summary()


# ── Dashboard Route ───────────────────────────────────────────────────────

@app.get("/")
def serve_dashboard():
    """Serve the main dashboard HTML file."""
    return FileResponse("dashboard/index.html")


@app.get("/login")
def serve_login():
    """Serve the login page."""
    return FileResponse("dashboard/login.html")


# ── Startup ───────────────────────────────────────────────────────────────

@app.on_event("startup")
def startup():
    """Initialize database on startup."""
    init_db()
    print("✓ Database initialised")
    print("✓ API ready at http://localhost:8000")
    print("✓ API docs at http://localhost:8000/docs")