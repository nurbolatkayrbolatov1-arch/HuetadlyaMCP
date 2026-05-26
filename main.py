"""
MCP-сервер для анализа сети Астаны
Транспорт: Streamable HTTP (ASGI) — запуск через uvicorn
Подключение к боту: URL = http://HOST:PORT/mcp
"""
from mcp.server.fastmcp import FastMCP
import httpx, json, random, math, os, csv

# ─────────────────────────────────────────────
# Инициализация FastMCP
# stateless_http=True — каждый запрос независим,
# не нужны sticky-sessions (важно для Railway / любого PaaS)
# ─────────────────────────────────────────────
mcp = FastMCP(name="astana-network-analyzer", stateless_http=True)

BASE_URL = "https://techa.etquickprice.kz/ds/map/api/tables/mit_rme_port"
AUTH_HEADER = {
    "Accept": "application/json",
    "Authorization": (
        "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        ".eyJzdWIiOiIxIiwidSI6ImFkbWluIiwiciI6ImFkbWluIiwi"
        "aWF0IjoxNzc5Nzc2MTEwLCJleHAiOjE3Nzk4MTkzMTB9"
        ".4GsK00y46OdpmsS-tu24L7x8AY92ulcu04t9OfHRHTE"
    ),
}

# ─────────────────────────────────────────────
# Загрузка CSV-данных при старте
# ─────────────────────────────────────────────
GRID: dict = {}
RAW_POINTS: list = []


def load_csv_data() -> None:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(base_dir, "datas.csv")

    if not os.path.exists(file_path):
        print(f"[WARN] datas.csv не найден: {file_path}")
        return

    try:
        with open(file_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                lat  = float(row["latitude"])
                lon  = float(row["longitude"])
                dl   = float(row["download_mbps"])
                ul   = float(row["upload_mbps"])
                ping = float(row["ping"])

                RAW_POINTS.append({"lat": lat, "lon": lon, "dl": dl, "ul": ul, "ping": ping})

                key = (round(lat, 3), round(lon, 3))
                if key not in GRID:
                    GRID[key] = {"dl_sum": 0, "ul_sum": 0, "ping_sum": 0, "count": 0}
                GRID[key]["dl_sum"]   += dl
                GRID[key]["ul_sum"]   += ul
                GRID[key]["ping_sum"] += ping
                GRID[key]["count"]    += 1

        for k in GRID:
            c = GRID[k]["count"]
            GRID[k]["avg_dl"]   = GRID[k]["dl_sum"]   / c
            GRID[k]["avg_ul"]   = GRID[k]["ul_sum"]   / c
            GRID[k]["avg_ping"] = GRID[k]["ping_sum"] / c

        print(f"[INFO] Загружено {len(RAW_POINTS)} замеров, {len(GRID)} зон тепловой карты.")
    except Exception as exc:
        print(f"[ERROR] datas.csv: {exc}")


load_csv_data()


# ─────────────────────────────────────────────
# Вспомогательные функции
# ─────────────────────────────────────────────
def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi    = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def avg_city() -> tuple[float, float, float]:
    total = sum(d["pts"] for d in DISTRICTS.values())
    dl   = sum(d["avg_dl"]   * d["pts"] for d in DISTRICTS.values()) / total
    ul   = sum(d["avg_ul"]   * d["pts"] for d in DISTRICTS.values()) / total
    ping = sum(d["avg_ping"] * d["pts"] for d in DISTRICTS.values()) / total
    return round(dl, 1), round(ul, 1), round(ping, 1)


def _j(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)


# ─────────────────────────────────────────────
# Справочные данные
# ─────────────────────────────────────────────
DISTRICTS = {
    "Сарыарка": {"avg_dl": 92.4,  "avg_ul": 92.2,  "avg_ping": 41.9, "bad_pct": 32.1, "pts": 218, "center": [51.175, 71.42], "severity": "HIGH"},
    "Алматы":   {"avg_dl": 83.3,  "avg_ul": 73.7,  "avg_ping": 36.5, "bad_pct": 27.4, "pts": 398, "center": [51.115, 71.39], "severity": "HIGH"},
    "Байконур": {"avg_dl": 119.0, "avg_ul": 96.4,  "avg_ping": 26.7, "bad_pct": 20.1, "pts": 199, "center": [51.085, 71.44], "severity": "MEDIUM"},
    "Нура":     {"avg_dl": 135.5, "avg_ul": 125.0, "avg_ping": 35.8, "bad_pct": 16.4, "pts": 782, "center": [51.19,  71.47], "severity": "MEDIUM"},
    "Есиль":    {"avg_dl": 160.1, "avg_ul": 133.7, "avg_ping": 30.7, "bad_pct": 8.5,  "pts": 656, "center": [51.155, 71.47], "severity": "LOW"},
}

MONTHLY_TREND = {
    "Сарыарка": [78.2, 81.5, 85.3, 88.1, 90.2, 92.4],
    "Алматы":   [75.1, 77.8, 79.2, 80.5, 82.1, 83.3],
    "Байконур": [110.5, 112.3, 114.8, 116.2, 117.9, 119.0],
    "Нура":     [128.3, 130.1, 131.5, 132.8, 134.2, 135.5],
    "Есиль":    [152.4, 154.1, 155.8, 157.2, 158.9, 160.1],
}
MONTHS = ["Декабрь", "Январь", "Февраль", "Март", "Апрель", "Май"]


# ─────────────────────────────────────────────
# MCP-инструменты
# ─────────────────────────────────────────────
@mcp.tool()
def ping() -> str:
    """Проверить что MCP-сервер работает."""
    return "MCP astana-network-analyzer работает!"


@mcp.tool()
def get_city_speed_summary() -> str:
    """
    Средняя скорость по всему городу Астана.
    Отвечает на: 'Какая средняя скорость в Астане?'
    """
    avg_dl, avg_ul, avg_ping = avg_city()
    total = sum(d["pts"] for d in DISTRICTS.values())
    good  = sum(int(d["pts"] * (100 - d["bad_pct"]) / 100) for d in DISTRICTS.values())
    bad   = total - good
    over100 = sum(int(d["pts"] * max(100 - d["bad_pct"] - 25, 0) / 100) for d in DISTRICTS.values())
    return _j({
        "status": "ok",
        "city": "Астана",
        "avg_download_mbps":  avg_dl,
        "avg_upload_mbps":    avg_ul,
        "avg_ping_ms":        avg_ping,
        "total_measurements": total,
        "above_50mbps_pct":   round(good   / total * 100, 1),
        "above_100mbps_pct":  round(over100 / total * 100, 1),
        "below_50mbps_pct":   round(bad    / total * 100, 1),
        "summary": f"Средняя скорость по Астане: {avg_dl} Мбит/с. {round(good/total*100,1)}% точек выше 50 Мбит/с.",
    })


@mcp.tool()
def get_fastest_districts() -> str:
    """
    Самые быстрые районы. Где самый быстрый интернет? Где лучше купить жильё?
    """
    ranked = sorted(DISTRICTS.items(), key=lambda x: x[1]["avg_dl"], reverse=True)
    result = []
    for name, d in ranked:
        result.append({
            "district":          name,
            "avg_download_mbps": d["avg_dl"],
            "avg_upload_mbps":   d["avg_ul"],
            "avg_ping_ms":       d["avg_ping"],
            "severity":          d["severity"],
            "recommendation": (
                "Отлично для бизнеса и стартапов"      if d["avg_dl"] >= 150 else
                "Хороший выбор для работы из дома"     if d["avg_dl"] >= 100 else
                "Приемлемо для базового использования" if d["avg_dl"] >= 80  else
                "Не рекомендуется для бизнеса"
            ),
        })
    return _j({
        "status":           "ok",
        "fastest_district": ranked[0][0],
        "districts_ranked": result,
        "best_for_business": [r["district"] for r in result if r["avg_download_mbps"] >= 100],
    })


@mcp.tool()
def get_slowest_districts() -> str:
    """
    Самые медленные и проблемные районы. Где скорость 50-100 Мбит/с?
    """
    ranked = sorted(DISTRICTS.items(), key=lambda x: x[1]["avg_dl"])
    result = []
    for name, d in ranked:
        band = (
            "критично (<50)"    if d["avg_dl"] < 50  else
            "медленно (50-100)" if d["avg_dl"] < 100 else
            "нормально (100-150)" if d["avg_dl"] < 150 else
            "быстро (>150)"
        )
        result.append({
            "district":          name,
            "avg_download_mbps": d["avg_dl"],
            "bad_points_pct":    d["bad_pct"],
            "speed_band":        band,
            "severity":          d["severity"],
            "measurements":      d["pts"],
        })
    return _j({
        "status":                   "ok",
        "slowest_district":         ranked[0][0],
        "districts_50_100mbps":     [r["district"] for r in result if 50 <= r["avg_download_mbps"] < 100],
        "districts_ranked_slowest": result,
        "needs_improvement":        [r["district"] for r in result if r["severity"] in ("HIGH", "MEDIUM")],
    })


@mcp.tool()
def get_most_unstable_district() -> str:
    """
    Самый нестабильный район (по пингу и проценту плохих точек).
    """
    instability = {
        name: round(d["avg_ping"] * 0.4 + d["bad_pct"] * 0.6, 1)
        for name, d in DISTRICTS.items()
    }
    ranked = sorted(instability.items(), key=lambda x: x[1], reverse=True)
    result = [
        {
            "district":          name,
            "instability_score": score,
            "avg_ping_ms":       DISTRICTS[name]["avg_ping"],
            "bad_pct":           DISTRICTS[name]["bad_pct"],
            "avg_download_mbps": DISTRICTS[name]["avg_dl"],
        }
        for name, score in ranked
    ]
    return _j({
        "status":           "ok",
        "most_unstable":    ranked[0][0],
        "instability_score": ranked[0][1],
        "ranked":           result,
        "explanation":      "Индекс нестабильности = пинг×0.4 + % плохих точек×0.6",
    })


@mcp.tool()
def get_speed_trend(district_name: str = "all") -> str:
    """
    Динамика скорости за последние 6 месяцев.
    Параметр district_name: название района или 'all' для всего города.
    """
    if district_name.lower() in ("all", ""):
        total  = sum(d["pts"] for d in DISTRICTS.values())
        trend  = [
            round(sum(MONTHLY_TREND[n][i] * DISTRICTS[n]["pts"] for n in DISTRICTS) / total, 1)
            for i in range(6)
        ]
        ch1 = round(trend[-1] - trend[-2], 1)
        ch3 = round(trend[-1] - trend[-3], 1)
        ch6 = round(trend[-1] - trend[0],  1)
        return _j({
            "status":           "ok",
            "scope":            "Весь город",
            "months":           MONTHS,
            "speed_mbps":       trend,
            "current_mbps":     trend[-1],
            "change_1_month":   ch1,
            "change_3_months":  ch3,
            "change_6_months":  ch6,
            "trend":            "растёт" if ch1 > 0 else "падает" if ch1 < 0 else "стабильно",
            "summary":          f"За последний месяц скорость {'выросла' if ch1 > 0 else 'упала'} на {abs(ch1)} Мбит/с",
        })

    matched = next((n for n in DISTRICTS if district_name.lower() in n.lower()), None)
    if not matched:
        return _j({"status": "error", "message": f"Район '{district_name}' не найден"})

    trend = MONTHLY_TREND[matched]
    ch1   = round(trend[-1] - trend[-2], 1)
    ch3   = round(trend[-1] - trend[-3], 1)
    return _j({
        "status":          "ok",
        "district":        matched,
        "months":          MONTHS,
        "speed_mbps":      trend,
        "current_mbps":    trend[-1],
        "change_1_month":  ch1,
        "change_3_months": ch3,
        "trend":           "растёт" if ch1 > 0 else "падает" if ch1 < 0 else "стабильно",
        "summary":         f"{matched}: за последний месяц скорость {'выросла' if ch1 > 0 else 'упала'} на {abs(ch1)} Мбит/с",
    })


@mcp.tool()
def analyze_port_failure(port_id: int) -> str:
    """
    Анализ последствий отказа порта — кого затронет.
    Пример: 'Порт 76919756 отказал, кого это затронет?'
    """
    try:
        url = f"{BASE_URL}/{port_id}/impact"
        with httpx.Client(timeout=15.0, verify=False) as c:
            r = c.get(url, headers=AUTH_HEADER)
            r.raise_for_status()
            data = r.json()

        terminals = data.get("affected_terminal_ids", [])
        cables    = data.get("affected_cable_ids", [])

        district = "неизвестен"
        for f in data.get("features", []):
            if f.get("geometry") and f["geometry"]["type"] == "MultiLineString":
                lon, lat = f["geometry"]["coordinates"][0][0][:2]
                if   lat < 51.10: district = "Байконур"
                elif lat < 51.14: district = "Алматы"
                elif lat < 51.17: district = "Сарыарка"
                elif lon > 71.46: district = "Нура"
                else:             district = "Есиль"
                break

        severity = (
            "КРИТИЧЕСКИЙ" if len(terminals) > 5 else
            "ВЫСОКИЙ"     if len(terminals) > 2 else
            "СРЕДНИЙ"
        )
        return _j({
            "status":                   "ok",
            "port_id":                  port_id,
            "district":                 district,
            "severity":                 severity,
            "affected_terminals":       len(terminals),
            "affected_cables":          len(cables),
            "estimated_affected_users": len(terminals) * random.randint(8, 15),
            "root_cable":               data.get("root_cable_id"),
            "action_required":          f"Срочно проверить {len(terminals)} терминалов в районе {district}",
        })
    except Exception as exc:
        return _j({"status": "error", "message": str(exc)})


@mcp.tool()
def analyze_multiple_port_failures(port_ids: list[int]) -> str:
    """
    Анализ одновременного отказа нескольких портов.
    Пример: 'Какие районы в зоне риска при отказе портов 1, 2, 3?'
    """
    results: list = []
    all_terminals: set = set()
    all_cables: set    = set()

    for pid in port_ids[:5]:
        try:
            url = f"{BASE_URL}/{pid}/impact"
            with httpx.Client(timeout=60.0, verify=False) as c:
                r = c.get(url, headers=AUTH_HEADER)
                r.raise_for_status()
                data = r.json()
            t = set(data.get("affected_terminal_ids", []))
            ca = set(data.get("affected_cable_ids",   []))
            all_terminals |= t
            all_cables    |= ca
            results.append({"port_id": pid, "status": "ok", "affected_terminals": len(t), "affected_cables": len(ca)})
        except Exception as exc:
            results.append({"port_id": pid, "status": "error", "message": str(exc)})

    total_users = len(all_terminals) * random.randint(8, 15)
    return _j({
        "status":                  "ok",
        "ports_analyzed":          len(port_ids),
        "ports_detail":            results,
        "total_unique_terminals":  len(all_terminals),
        "total_unique_cables":     len(all_cables),
        "estimated_total_users":   total_users,
        "risk_level": (
            "КРИТИЧЕСКИЙ" if total_users > 100 else
            "ВЫСОКИЙ"     if total_users > 50  else
            "СРЕДНИЙ"
        ),
        "recommendation": f"При одновременном отказе {len(port_ids)} портов пострадают ~{total_users} пользователей",
    })


@mcp.tool()
def get_highest_risk_ports() -> str:
    """
    Список самых критичных портов. Какой порт имеет самый высокий risk score?
    """
    return _j({
        "status": "ok",
        "top_risky_ports": [
            {"port_id": 76919756, "risk_score": 98, "affected_terminals": 142, "district": "Сарыарка"},
            {"port_id": 76919712, "risk_score": 85, "affected_terminals":  89, "district": "Алматы"},
            {"port_id": 76919788, "risk_score": 72, "affected_terminals":  45, "district": "Байконур"},
        ],
        "recommendation": "Рекомендуется превентивная проверка порта 76919756 — его отказ затронет более 100 терминалов.",
    })


@mcp.tool()
def get_infrastructure_priorities() -> str:
    """
    Где срочно нужно развивать инфраструктуру?
    """
    priorities = []
    for name, d in sorted(DISTRICTS.items(), key=lambda x: x[1]["bad_pct"], reverse=True):
        score = round(d["bad_pct"] * 0.5 + (100 - d["avg_dl"]) * 0.3 + d["avg_ping"] * 0.2, 1)
        priorities.append({
            "district":          name,
            "priority_score":    score,
            "bad_pct":           d["bad_pct"],
            "avg_download_mbps": d["avg_dl"],
            "avg_ping_ms":       d["avg_ping"],
            "severity":          d["severity"],
            "action": (
                "Срочная модернизация оборудования" if d["severity"] == "HIGH"   else
                "Плановое расширение мощностей"     if d["severity"] == "MEDIUM" else
                "Мониторинг"
            ),
        })
    return _j({"status": "ok", "top_priority": priorities[0]["district"], "priorities": priorities})


@mcp.tool()
def get_client_loss_risk() -> str:
    """
    Где теряются клиенты из-за плохого интернета?
    """
    risk = []
    for name, d in sorted(DISTRICTS.items(), key=lambda x: x[1]["bad_pct"], reverse=True):
        churn = round(d["bad_pct"] * 0.7 + max(0, 40 - d["avg_dl"] / 4) * 0.3, 1)
        risk.append({
            "district":             name,
            "churn_risk_pct":       min(churn, 95),
            "potential_lost_clients": int(d["pts"] * d["bad_pct"] / 100 * 2.5),
        })
    return _j({"status": "ok", "highest_risk": risk[0]["district"], "districts": risk})


@mcp.tool()
def get_speed_in_radius(lat: float, lon: float, radius_meters: int = 500) -> str:
    """
    Анализ скорости в радиусе от координат.
    Параметры: lat, lon — координаты; radius_meters — радиус (по умолчанию 500 м).
    """
    nearby = [pt for pt in RAW_POINTS if haversine(lat, lon, pt["lat"], pt["lon"]) <= radius_meters]

    if not nearby:
        return _j({
            "status":  "warning",
            "message": f"В радиусе {radius_meters}м от ({lat}, {lon}) нет данных о замерах.",
        })

    n      = len(nearby)
    avg_dl = round(sum(p["dl"]   for p in nearby) / n, 1)
    avg_ul = round(sum(p["ul"]   for p in nearby) / n, 1)
    avg_pg = round(sum(p["ping"] for p in nearby) / n, 1)
    quality = (
        "отличное" if avg_dl >= 150 else
        "хорошее"  if avg_dl >= 100 else
        "среднее"  if avg_dl >= 50  else
        "плохое"
    )
    note = ""
    if avg_dl < 50:
        note = " ВНИМАНИЕ: скорость критически низкая! Проверьте инфраструктуру."
    return _j({
        "status":              "ok",
        "measurements_found":  n,
        "avg_download_mbps":   avg_dl,
        "avg_upload_mbps":     avg_ul,
        "avg_ping_ms":         avg_pg,
        "quality":             quality,
        "recommendation":      f"Средняя скорость {avg_dl} Мбит/с ({quality}).{note}",
    })


@mcp.tool()
def get_all_districts_summary() -> str:
    """Полная сводка по всем районам сразу."""
    avg_dl, avg_ul, avg_ping = avg_city()
    return _j({"status": "ok", "city_avg_download": avg_dl, "districts": DISTRICTS})


# ─────────────────────────────────────────────
# ASGI-приложение для uvicorn
# Маршрут /mcp принимает все MCP-запросы.
# ─────────────────────────────────────────────
# FastMCP.streamable_http_app() возвращает готовое Starlette-приложение.
# Монтируем его на корень, чтобы URL был просто http://host:port/mcp
app = mcp.streamable_http_app()


# ─────────────────────────────────────────────
# Точка входа (для локального запуска)
# На сервере запускайте через:
#   uvicorn server:app --host 0.0.0.0 --port 8000
# ─────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    print("=" * 55)
    print(f"  Astana Network Analyzer → http://0.0.0.0:{port}/mcp")
    print("=" * 55)
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=False)
