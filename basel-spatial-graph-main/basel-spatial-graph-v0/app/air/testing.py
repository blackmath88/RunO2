"""A small deterministic street grid, so every test asserts against truth.

Not a fixture of Basel — a grid over the same bounding box the fixture air
source uses, dense enough that loops of a few kilometres exist and coarse
enough that the whole suite stays fast.
"""
from __future__ import annotations

import networkx as nx

from .projection_compat import to_metric
from .sources.fixture_source import DEFAULT_BBOX


def fixture_network(bbox=DEFAULT_BBOX, cols: int = 12, rows: int = 10):
    west, south, east, north = bbox
    graph = nx.Graph()
    for r in range(rows):
        for c in range(cols):
            lon = west + (east - west) * (c / (cols - 1))
            lat = south + (north - south) * (r / (rows - 1))
            (x,), (y,) = to_metric([lon], [lat])
            graph.add_node(f"n{r}_{c}", lon=lon, lat=lat, x=x, y=y)

    def _add(a, b):
        na, nb = graph.nodes[a], graph.nodes[b]
        length = ((na["x"] - nb["x"]) ** 2 + (na["y"] - nb["y"]) ** 2) ** 0.5
        graph.add_edge(a, b, length_m=length)

    for r in range(rows):
        for c in range(cols):
            if c + 1 < cols:
                _add(f"n{r}_{c}", f"n{r}_{c+1}")
            if r + 1 < rows:
                _add(f"n{r}_{c}", f"n{r+1}_{c}")
    return graph


CENTRE = ((DEFAULT_BBOX[0] + DEFAULT_BBOX[2]) / 2, (DEFAULT_BBOX[1] + DEFAULT_BBOX[3]) / 2)
