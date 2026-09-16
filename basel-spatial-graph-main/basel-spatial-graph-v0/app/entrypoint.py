"""Deployment entrypoint for the RunO2 product surface.

The underlying FastAPI application also contains the Basel Spatial Graph
reference UI. For the RunO2 repository deployment, make RunO2 the public root
while keeping the reference UI available at /spatial-graph.
"""
from fastapi.responses import FileResponse

from .config import STATIC_DIR
from .main import app

# Remove only the legacy reference application's root route. All APIs and the
# existing /run routes remain untouched.
app.router.routes = [
    route
    for route in app.router.routes
    if not (getattr(route, "path", None) == "/" and getattr(route, "name", None) == "root")
]


@app.get("/", include_in_schema=False)
def runo2_root():
    """Serve the RunO2 experience as the primary deployed surface."""
    return FileResponse(STATIC_DIR / "run.html")


@app.get("/spatial-graph", include_in_schema=False)
def spatial_graph_reference_ui():
    """Keep the original 15-Minute Basel reference UI accessible."""
    return FileResponse(STATIC_DIR / "index.html")
