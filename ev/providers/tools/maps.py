"""Location/maps tools (OpenStreetMap-based, no API key)."""

from __future__ import annotations

import logging
import re

log = logging.getLogger("ev.tools")


def reverse_geocode(lat: float, lng: float) -> str:
    """Best-effort human-readable address for coordinates (OpenStreetMap/Nominatim)."""
    import json
    import urllib.request
    url = (f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lng}"
           "&format=json&zoom=16&addressdetails=0")
    req = urllib.request.Request(url, headers={"User-Agent": "E.V.-assistant/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=6) as r:
            data = json.loads(r.read().decode())
        return (data.get("display_name") or "").strip()
    except Exception as exc:
        log.warning("reverse_geocode failed (%s)", exc)
        return ""


# Friendly place types -> OpenStreetMap tag filters (for Overpass queries).
_OSM_KINDS = {
    "farmácia": '["amenity"="pharmacy"]', "farmacia": '["amenity"="pharmacy"]',
    "mercado": '["shop"~"supermarket|convenience|grocery"]',
    "supermercado": '["shop"="supermarket"]',
    "restaurante": '["amenity"="restaurant"]',
    "padaria": '["shop"="bakery"]',
    "café": '["amenity"="cafe"]', "cafe": '["amenity"="cafe"]',
    "posto": '["amenity"="fuel"]', "gasolina": '["amenity"="fuel"]',
    "banco": '["amenity"="bank"]', "caixa": '["amenity"="atm"]',
    "hospital": '["amenity"~"hospital|clinic"]', "saúde": '["amenity"~"hospital|clinic|pharmacy"]',
    "ônibus": '["highway"="bus_stop"]', "onibus": '["highway"="bus_stop"]',
    "metrô": '["station"="subway"]', "metro": '["station"="subway"]',
    "trem": '["railway"="station"]', "estação": '["railway"="station"]',
    "academia": '["leisure"="fitness_centre"]',
    "escola": '["amenity"="school"]', "hotel": '["tourism"="hotel"]',
    "estacionamento": '["amenity"="parking"]',
}


def _haversine_m(lat1, lng1, lat2, lng2) -> int:
    from math import radians, sin, cos, asin, sqrt
    dlat, dlng = radians(lat2 - lat1), radians(lng2 - lng1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    return int(6371000 * 2 * asin(sqrt(a)))


def nearby_places(lat: float, lng: float, query: str, radius_m: int = 1600,
                  limit: int = 20) -> list[dict]:
    """Find POIs near (lat,lng) via OpenStreetMap Overpass. Returns items sorted
    by distance: {name, lat, lng, dist, kind}. Empty list on any failure."""
    import json
    import urllib.parse
    import urllib.request

    q = (query or "").strip().lower()
    flt = _OSM_KINDS.get(q)
    if flt:
        selector = f"nwr{flt}(around:{radius_m},{lat},{lng});"
    else:  # free text -> match by name
        safe = re.sub(r'["\\]', "", query.strip())[:40]
        selector = f'nwr["name"~"{safe}",i](around:{radius_m},{lat},{lng});'
    oql = f"[out:json][timeout:25];({selector});out center {limit * 3};"
    data = urllib.parse.urlencode({"data": oql}).encode()
    res = None
    for ep in ("https://overpass-api.de/api/interpreter",
               "https://overpass.kumi.systems/api/interpreter",
               "https://overpass.private.coffee/api/interpreter",
               "https://maps.mail.ru/osm/tools/overpass/api/interpreter"):
        try:
            req = urllib.request.Request(
                ep, data=data, headers={"User-Agent": "E.V.-assistant/1.0"})
            with urllib.request.urlopen(req, timeout=25) as r:
                res = json.loads(r.read().decode())
            break
        except Exception as exc:
            log.warning("nearby_places via %s failed (%s)", ep.split("/")[2], exc)
    if res is None:
        return []
    out = []
    for e in res.get("elements", []):
        tags = e.get("tags", {})
        name = tags.get("name")
        if not name:
            continue
        plat = e.get("lat") or (e.get("center") or {}).get("lat")
        plng = e.get("lon") or (e.get("center") or {}).get("lon")
        if plat is None or plng is None:
            continue
        out.append({
            "name": name, "lat": plat, "lng": plng,
            "dist": _haversine_m(lat, lng, plat, plng),
            "kind": tags.get("amenity") or tags.get("shop") or tags.get("leisure") or "",
        })
    out.sort(key=lambda p: p["dist"])
    # dedupe by name, keep nearest
    seen, uniq = set(), []
    for p in out:
        k = p["name"].lower()
        if k in seen:
            continue
        seen.add(k)
        uniq.append(p)
    return uniq[:limit]


def geocode(query: str) -> dict | None:
    """Forward-geocode an address/place to coords (OpenStreetMap/Nominatim)."""
    import json
    import urllib.parse
    import urllib.request
    url = ("https://nominatim.openstreetmap.org/search?"
           + urllib.parse.urlencode({"q": query, "format": "json", "limit": 1}))
    req = urllib.request.Request(url, headers={"User-Agent": "E.V.-assistant/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=9) as r:
            data = json.loads(r.read().decode())
        if not data:
            return None
        return {"lat": float(data[0]["lat"]), "lng": float(data[0]["lon"]),
                "name": data[0].get("display_name", "")}
    except Exception as exc:
        log.warning("geocode failed (%s)", exc)
        return None


def route(from_lat, from_lng, to_lat, to_lng, mode: str = "car") -> dict | None:
    """Driving/walking route between two points (OSRM, free). Returns
    {distance_m, duration_s, geometry(GeoJSON LineString)} or None."""
    import json
    import urllib.request
    prof = {"foot": "routed-foot", "bike": "routed-bike"}.get(mode, "routed-car")
    pname = {"foot": "foot", "bike": "bike"}.get(mode, "driving")
    url = (f"https://routing.openstreetmap.de/{prof}/route/v1/{pname}/"
           f"{from_lng},{from_lat};{to_lng},{to_lat}?overview=full&geometries=geojson")
    req = urllib.request.Request(url, headers={"User-Agent": "E.V.-assistant/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=13) as r:
            data = json.loads(r.read().decode())
        rt = (data.get("routes") or [None])[0]
        if not rt:
            return None
        return {"distance": int(rt["distance"]), "duration": int(rt["duration"]),
                "geometry": rt["geometry"]}
    except Exception as exc:
        log.warning("route failed (%s)", exc)
        return None


def maps_search_link(lat, lng, query: str) -> str:
    """Google Maps search link for `query` near coordinates."""
    import urllib.parse
    return (f"https://www.google.com/maps/search/{urllib.parse.quote(query)}"
            f"/@{lat},{lng},15z")


def static_map_url(center_lat, center_lng, markers=None, zoom: int = 15,
                   w: int = 600, h: int = 320) -> str:
    """Free OpenStreetMap static-map image (no API key). `markers` = list of
    (lat, lng), pinned in red. It's a community service — best-effort, may be
    slow or occasionally unavailable; the route links work regardless."""
    import urllib.parse
    params = [("center", f"{center_lat},{center_lng}"), ("zoom", str(zoom)),
              ("size", f"{w}x{h}")]
    for mlat, mlng in (markers or []):
        params.append(("markers", f"{mlat},{mlng},red-pushpin"))
    return "https://staticmap.openstreetmap.de/staticmap.php?" + urllib.parse.urlencode(params)


def directions_link(from_lat, from_lng, to_lat, to_lng, mode: str = "walking") -> str:
    """Google Maps directions (route) link from the user's location to a place."""
    tm = mode if mode in ("walking", "driving", "bicycling", "transit") else "walking"
    return (f"https://www.google.com/maps/dir/?api=1&origin={from_lat},{from_lng}"
            f"&destination={to_lat},{to_lng}&travelmode={tm}")
