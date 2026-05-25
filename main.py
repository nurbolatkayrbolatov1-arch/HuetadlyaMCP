import os
from mcp.server.fastmcp import FastMCP
import httpx
import json

# 1. Получаем динамический порт от Railway (или 8000 для локального теста)
PORT = int(os.environ.get("PORT", 8000))

mcp = FastMCP(
    name="cable-network-analyzer",
    host="0.0.0.0",
    port=PORT,
)

BASE_URL = "https://techa.etquickprice.kz/ds/map/api/tables/mit_rme_port"


@mcp.tool()
def ping() -> str:
    """Проверить что MCP-сервер работает."""
    return "MCP работает!"


@mcp.tool()
def check_api(port_id: int = 76919823) -> str:
    """Проверить доступность API и вернуть данные по порту."""
    try:
        url = f"{BASE_URL}/{port_id}/impact"
        with httpx.Client(timeout=60.0, verify=False) as client:
            resp = client.get(url, headers={"Accept": "application/json"})
            resp.raise_for_status()
            data = resp.json()
        return json.dumps({
            "status": "ok",
            "port_id": port_id,
            "counts": data.get("counts", {}),
            "affected_cables": len(data.get("affected_cable_ids", [])),
            "affected_terminals": len(data.get("affected_terminal_ids", [])),
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})


@mcp.tool()
def get_cable_impact(port_id: int) -> str:
    """Получить сводку по кабелям для порта."""
    try:
        url = f"{BASE_URL}/{port_id}/impact"
        with httpx.Client(timeout=15.0, verify=False) as client:
            resp = client.get(url, headers={"Accept": "application/json"})
            resp.raise_for_status()
            data = resp.json()
        affected_ids = set(data.get("affected_cable_ids", []))
        features = data.get("features", [])
        cables_with_geo = [f for f in features if f["properties"]["kind"] == "cable" and f["geometry"]]
        cables_no_geo   = [f for f in features if f["properties"]["kind"] == "cable" and not f["geometry"]]
        return json.dumps({
            "status": "ok",
            "port_id": port_id,
            "root_cable_id": data.get("root_cable_id"),
            "counts": data.get("counts", {}),
            "cables_with_coordinates": len(cables_with_geo),
            "cables_without_coordinates": len(cables_no_geo),
            "affected_cables_count": len(affected_ids),
            "affected_terminal_ids": data.get("affected_terminal_ids", []),
        }, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})


@mcp.tool()
def get_problem_zones(port_id: int) -> str:
    """Найти проблемные кабели с нагрузкой или без координат."""
    try:
        url = f"{BASE_URL}/{port_id}/impact"
        with httpx.Client(timeout=15.0, verify=False) as client:
            resp = client.get(url, headers={"Accept": "application/json"})
            resp.raise_for_status()
            data = resp.json()
        affected_ids = set(data.get("affected_cable_ids", []))
        seen_ids = set()
        problems = []
        for f in data.get("features", []):
            fid = f["id"]
            if fid in seen_ids:
                continue
            seen_ids.add(fid)
            props = f["properties"]
            if props["kind"] != "cable":
                continue
            extra   = props.get("extra")
            has_geo = f["geometry"] is not None
            if extra is not None or not has_geo:
                coords = None
                if has_geo and f["geometry"]["type"] == "MultiLineString":
                    line = f["geometry"]["coordinates"][0]
                    coords = {"start": line[0], "end": line[-1]}
                severity = (
                    "HIGH"   if extra is not None and not has_geo else
                    "MEDIUM" if extra is not None else "LOW"
                )
                problems.append({
                    "id": fid, "name": props["name"],
                    "extra_load": extra, "has_geometry": has_geo,
                    "is_affected": fid in affected_ids,
                    "severity": severity, "coordinates": coords,
                })
        problems.sort(key=lambda x: {"HIGH": 0, "MEDIUM": 1, "LOW": 2}[x["severity"]])
        return json.dumps({
            "status": "ok", "port_id": port_id,
            "total_problems": len(problems),
            "high": sum(1 for p in problems if p["severity"] == "HIGH"),
            "medium": sum(1 for p in problems if p["severity"] == "MEDIUM"),
            "low": sum(1 for p in problems if p["severity"] == "LOW"),
            "problems": problems,
        }, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})


@mcp.tool()
def traverse_problem_path(port_id: int) -> str:
    """Обойти затронутые кабели и вернуть маршрут с координатами."""
    try:
        url = f"{BASE_URL}/{port_id}/impact"
        with httpx.Client(timeout=15.0, verify=False) as client:
            resp = client.get(url, headers={"Accept": "application/json"})
            resp.raise_for_status()
            data = resp.json()
        affected_ids = set(data.get("affected_cable_ids", []))
        seen_ids = set()
        path = []
        for f in data.get("features", []):
            fid = f["id"]
            if fid in seen_ids or not f["geometry"] or fid not in affected_ids:
                continue
            seen_ids.add(fid)
            if f["properties"]["kind"] != "cable":
                continue
            for line in f["geometry"].get("coordinates", []):
                path.append({
                    "cable_id": fid,
                    "name": f["properties"]["name"],
                    "extra_load": f["properties"].get("extra"),
                    "start": {"lon": line[0][0], "lat": line[0][1]},
                    "end":   {"lon": line[-1][0], "lat": line[-1][1]},
                    "points": len(line),
                })
        return json.dumps({
            "status": "ok", "port_id": port_id,
            "segments": len(path), "path": path,
        }, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})


# 2. Инструмент get_map_html перенесен ВЫШЕ блока запуска сервера
@mcp.tool()
def get_map_html(port_id: int) -> str:
    """Сгенерировать интерактивную HTML-карту кабельной сети для порта."""
    try:
        url = f"{BASE_URL}/{port_id}/impact"
        with httpx.Client(timeout=15.0, verify=False) as client:
            resp = client.get(url, headers={"Accept": "application/json"})
            resp.raise_for_status()
            data = resp.json()

        affected_ids = set(data.get("affected_cable_ids", []))
        seen_ids = set()
        cables = []
        splices = []
        terminals = []
        buildings = []

        for f in data.get("features", []):
            fid = f["id"]
            kind = f["properties"]["kind"]
            geo  = f["geometry"]

            if kind == "cable" and geo and fid not in seen_ids:
                seen_ids.add(fid)
                extra = f["properties"].get("extra")
                is_aff = fid in affected_ids
                color = "#E24B4A" if (is_aff and extra) else "#EF9F27" if is_aff else "#378ADD"
                for line in geo.get("coordinates", []):
                    cables.append({"coords": [[c[1], c[0]] for c in line],
                                   "color": color, "name": f["properties"]["name"],
                                   "extra": extra, "id": fid})

            elif kind == "splice" and geo:
                pt = geo.get("coordinates", [])
                if pt:
                    splices.append({"lat": pt[1], "lon": pt[0], "name": f["properties"]["name"]})

            elif kind == "terminal" and geo:
                pts = geo.get("coordinates", [[]])[0] if geo["type"] == "MultiPoint" else geo.get("coordinates", [])
                if pts:
                    terminals.append({"lat": pts[1], "lon": pts[0], "name": f["properties"]["name"],
                                      "affected": fid in data.get("affected_terminal_ids", [])})

            elif kind == "building" and geo:
                coords = geo.get("coordinates", [[[[]]]])[0][0]
                if coords:
                    lat = sum(c[1] for c in coords) / len(coords)
                    lon = sum(c[0] for c in coords) / len(coords)
                    buildings.append({"lat": lat, "lon": lon, "name": f["properties"]["name"]})

        counts = data.get("counts", {})
        cables_js   = json.dumps(cables)
        splices_js  = json.dumps(splices)
        terminals_js = json.dumps(terminals)
        buildings_js = json.dumps(buildings)

        html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Карта кабельной сети — порт {port_id}</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css"/>
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family: sans-serif; }}
  #map {{ width:100%; height:100vh; }}
  #panel {{ position:absolute; top:10px; left:50px; z-index:1000; background:#fff;
            border-radius:8px; padding:12px 16px; box-shadow:0 2px 8px rgba(0,0,0,.15); min-width:220px; }}
  #panel h3 {{ font-size:14px; margin-bottom:8px; color:#333; }}
  .stat {{ display:flex; justify-content:space-between; font-size:13px; padding:2px 0; color:#555; }}
  .stat b {{ color:#222; }}
  .legend {{ margin-top:10px; padding-top:8px; border-top:1px solid #eee; }}
  .leg {{ display:flex; align-items:center; gap:6px; font-size:12px; color:#555; margin:3px 0; }}
  .line {{ width:20px; height:3px; border-radius:2px; }}
  .dot {{ width:10px; height:10px; border-radius:50%; }}
</style>
</head>
<body>
<div id="panel">
  <h3>📡 Порт {port_id}</h3>
  <div class="stat"><span>Кабелей</span><b>{counts.get("cables", "—")}</b></div>
  <div class="stat"><span>Сплайсов</span><b>{counts.get("splices", "—")}</b></div>
  <div class="stat"><span>Терминалов</span><b>{counts.get("terminals", "—")}</b></div>
  <div class="stat"><span>Затронуто портов</span><b>{counts.get("affected_ports", "—")}</b></div>
  <div class="legend">
    <div class="leg"><div class="line" style="background:#E24B4A"></div>критический</div>
    <div class="leg"><div class="line" style="background:#EF9F27"></div>затронут</div>
    <div class="leg"><div class="line" style="background:#378ADD"></div>норма</div>
    <div class="leg"><div class="dot" style="background:#1D9E75"></div>сплайс</div>
    <div class="leg"><div class="dot" style="background:#E24B4A"></div>терминал ⚠️</div>
  </div>
</div>
<div id="map"></div>
<script>
const map = L.map('map').setView([51.168, 71.435], 13);
L.tileLayer('https://tile{{s}}.maps.2gis.com/tiles?x={{x}}&y={{y}}&z={{z}}&v=1.5', {{
  subdomains: '0123',
  attribution: '© 2GIS',
  maxZoom: 18,
}}).addTo(map);

const cables = {cables_js};
cables.forEach(c => {{
  L.polyline(c.coords, {{color: c.color, weight: 2.5, opacity: 0.85}})
   .addTo(map)
   .bindPopup(`<b>${{c.name}}</b><br>ID: ${{c.id}}<br>Extra: ${{c.extra ?? '—'}}`);
}});

const splices = {splices_js};
splices.forEach(s => {{
  L.circleMarker([s.lat, s.lon], {{radius:6, fillColor:'#1D9E75', color:'#fff', weight:2, fillOpacity:1}})
   .addTo(map).bindPopup(`<b>Сплайс</b><br>${{s.name}}`);
}});

const terminals = {terminals_js};
terminals.forEach(t => {{
  L.circleMarker([t.lat, t.lon], {{radius:7, fillColor: t.affected ? '#E24B4A' : '#888',
    color:'#fff', weight:2, fillOpacity:1}})
   .addTo(map).bindPopup(`<b>Терминал</b><br>${{t.name}}${{t.affected ? '<br>⚠️ Затронут' : ''}}`);
}});

const buildings = {buildings_js};
buildings.forEach(b => {{
  L.marker([b.lat, b.lon], {{
    icon: L.divIcon({{className:'', html:`<div style="background:#534AB7;color:#fff;font-size:11px;padding:2px 6px;border-radius:4px;white-space:nowrap">${{b.name}}</div>`, iconAnchor:[0,10]}})
  }}).addTo(map);
}});
</script>
</body>
</html>"""

        import tempfile, os
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".html",
                                          mode="w", encoding="utf-8")
        tmp.write(html)
        tmp.close()
        return json.dumps({
            "status": "ok",
            "message": "Карта сгенерирована",
            "html_preview": html[:500] + "...",
            "full_html": html,
        }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})


if __name__ == "__main__":
    print("Инструменты: ping, check_api, get_cable_impact, get_problem_zones, traverse_problem_path, get_map_html")
    print(f"Запуск MCP сервера на порту {PORT}...")
    
    # 3. Запускаем сервер с транспортом sse, чтобы Alem AI мог к нему подключиться
    mcp.run(transport="sse")
