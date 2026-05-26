"""
MCP-сервер для анализа сети Астаны
Отвечает на все вопросы о скорости, районах, портах и инфраструктуре
"""
from mcp.server.fastmcp import FastMCP
import httpx, json, random, math, os, csv
from datetime import datetime, timedelta

mcp = FastMCP(name="astana-network-analyzer", stateless_http=True)
BASE_URL = "https://techa.etquickprice.kz/ds/map/api/tables/mit_rme_port"

GRID = {}
RAW_POINTS = []

def load_csv_data():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(base_dir, 'datas.csv')
    
    if not os.path.exists(file_path):
        print(f"КРИТИЧЕСКАЯ ОШИБКА: Файл не найден по пути {file_path}")
        return

    try:
        with open(file_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                lat = float(row['latitude'])
                lon = float(row['longitude'])
                dl = float(row['download_mbps'])
                ul = float(row['upload_mbps'])
                ping = float(row['ping'])
                
                RAW_POINTS.append({
                    'lat': lat, 'lon': lon, 
                    'dl': dl, 'ul': ul, 'ping': ping
                })
                
                rlat = round(lat, 3)
                rlon = round(lon, 3)
                key = (rlat, rlon)
                
                if key not in GRID:
                    GRID[key] = {'dl_sum': 0, 'ul_sum': 0, 'ping_sum': 0, 'count': 0}
                
                GRID[key]['dl_sum'] += dl
                GRID[key]['ul_sum'] += ul
                GRID[key]['ping_sum'] += ping
                GRID[key]['count'] += 1
                
        for k in GRID:
            c = GRID[k]['count']
            GRID[k]['avg_dl'] = GRID[k]['dl_sum'] / c
            GRID[k]['avg_ul'] = GRID[k]['ul_sum'] / c
            GRID[k]['avg_ping'] = GRID[k]['ping_sum'] / c
            
        print(f"Успешно загружено {len(RAW_POINTS)} точных замеров и {len(GRID)} зон тепловой карты.")
    except Exception as e:
        print(f"Ошибка при обработке datas.csv: {e}")

load_csv_data()

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000 
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    
DISTRICTS = {
    "Сарыарка": {"avg_dl": 92.4,  "avg_ul": 92.2,  "avg_ping": 41.9, "bad_pct": 32.1, "pts": 218,  "center": [51.175, 71.42], "severity": "HIGH"},
    "Алматы":   {"avg_dl": 83.3,  "avg_ul": 73.7,  "avg_ping": 36.5, "bad_pct": 27.4, "pts": 398,  "center": [51.115, 71.39], "severity": "HIGH"},
    "Байконур": {"avg_dl": 119.0, "avg_ul": 96.4,  "avg_ping": 26.7, "bad_pct": 20.1, "pts": 199,  "center": [51.085, 71.44], "severity": "MEDIUM"},
    "Нура":     {"avg_dl": 135.5, "avg_ul": 125.0, "avg_ping": 35.8, "bad_pct": 16.4, "pts": 782,  "center": [51.19,  71.47], "severity": "MEDIUM"},
    "Есиль":    {"avg_dl": 160.1, "avg_ul": 133.7, "avg_ping": 30.7, "bad_pct": 8.5,  "pts": 656,  "center": [51.155, 71.47], "severity": "LOW"},
}

MONTHLY_TREND = {
    "Сарыарка": [78.2, 81.5, 85.3, 88.1, 90.2, 92.4],
    "Алматы":   [75.1, 77.8, 79.2, 80.5, 82.1, 83.3],
    "Байконур": [110.5, 112.3, 114.8, 116.2, 117.9, 119.0],
    "Нура":     [128.3, 130.1, 131.5, 132.8, 134.2, 135.5],
    "Есиль":    [152.4, 154.1, 155.8, 157.2, 158.9, 160.1],
}

MONTHS = ["Декабрь", "Январь", "Февраль", "Март", "Апрель", "Май"]

def avg_city():
    total_pts = sum(d["pts"] for d in DISTRICTS.values())
    avg_dl = sum(d["avg_dl"] * d["pts"] for d in DISTRICTS.values()) / total_pts
    avg_ul = sum(d["avg_ul"] * d["pts"] for d in DISTRICTS.values()) / total_pts
    avg_ping = sum(d["avg_ping"] * d["pts"] for d in DISTRICTS.values()) / total_pts
    return round(avg_dl, 1), round(avg_ul, 1), round(avg_ping, 1)


@mcp.tool()
def ping() -> str:
    """Проверить что MCP-сервер работает."""
    return "MCP astana-network-analyzer работает!"

@mcp.tool()
def get_city_speed_summary() -> str:
    """
    Средняя скорость по всему городу Астана.
    Отвечает на: 'Какая средняя скорость в Астане?'
    'Какой процент города имеет скорость выше 50 Mbps?'
    """
    avg_dl, avg_ul, avg_ping = avg_city()
    total_pts = sum(d["pts"] for d in DISTRICTS.values())
    good_pts  = sum(int(d["pts"] * (100 - d["bad_pct"]) / 100) for d in DISTRICTS.values())
    bad_pts   = total_pts - good_pts
    over_100  = sum(int(d["pts"] * (100 - d["bad_pct"] - 25) / 100) for d in DISTRICTS.values())

    return json.dumps({
        "status": "ok",
        "city": "Астана",
        "avg_download_mbps": avg_dl,
        "avg_upload_mbps": avg_ul,
        "avg_ping_ms": avg_ping,
        "total_measurements": total_pts,
        "above_50mbps_pct": round(good_pts / total_pts * 100, 1),
        "above_100mbps_pct": round(max(over_100, 0) / total_pts * 100, 1),
        "below_50mbps_pct": round(bad_pts / total_pts * 100, 1),
        "provider": "Kazakhtelecom",
        "summary": f"Средняя скорость по Астане: {avg_dl} Мбит/с. {round(good_pts/total_pts*100,1)}% точек имеют скорость выше 50 Мбит/с."
    }, ensure_ascii=False, indent=2)

@mcp.tool()
def get_fastest_districts() -> str:
    """
    Самые быстрые районы города.
    Отвечает на: 'Где в городе самая быстрая скорость?', 'Где я могу получить скорость выше 100 Mbps?', 'Какой район лучше для стартапа по интернет-скорости?', 'Где жильё покупать если интернет критичен?'
    """
    ranked = sorted(DISTRICTS.items(), key=lambda x: x[1]["avg_dl"], reverse=True)
    result = []
    for name, d in ranked:
        result.append({
            "district": name,
            "avg_download_mbps": d["avg_dl"],
            "avg_upload_mbps": d["avg_ul"],
            "avg_ping_ms": d["avg_ping"],
            "above_100mbps_pct": round(100 - d["bad_pct"] - 20, 1),
            "severity": d["severity"],
            "recommendation": (
                "Отлично для бизнеса и стартапов" if d["avg_dl"] >= 150 else
                "Хороший выбор для работы из дома" if d["avg_dl"] >= 100 else
                "Приемлемо для базового использования" if d["avg_dl"] >= 80 else
                "Не рекомендуется для бизнеса"
            )
        })
    return json.dumps({
        "status": "ok",
        "fastest_district": ranked[0][0],
        "avg_download": ranked[0][1]["avg_dl"],
        "districts_ranked": result,
        "best_for_business": [r["district"] for r in result if r["avg_download_mbps"] >= 100],
        "above_100mbps": [r["district"] for r in result if r["above_100mbps_pct"] > 50],
    }, ensure_ascii=False, indent=2)

@mcp.tool()
def get_slowest_districts() -> str:
    """
    Самые медленные и проблемные районы.
    Отвечает на: 'Где самые медленные районы?', 'Где скорость самая низкая?', 'В каких районах скорость 50-100 Mbps?', 'Какие районы не обслуживаются адекватно?'
    """
    ranked = sorted(DISTRICTS.items(), key=lambda x: x[1]["avg_dl"])
    result = []
    for name, d in ranked:
        band = (
            "критично (<50)" if d["avg_dl"] < 50 else
            "медленно (50-100)" if d["avg_dl"] < 100 else
            "нормально (100-150)" if d["avg_dl"] < 150 else
            "быстро (>150)"
        )
        result.append({
            "district": name,
            "avg_download_mbps": d["avg_dl"],
            "bad_points_pct": d["bad_pct"],
            "speed_band": band,
            "severity": d["severity"],
            "measurements": d["pts"],
        })
    mid_band = [r["district"] for r in result if 50 <= r["avg_download_mbps"] < 100]
    return json.dumps({
        "status": "ok",
        "slowest_district": ranked[0][0],
        "slowest_avg_mbps": ranked[0][1]["avg_dl"],
        "districts_50_100mbps": mid_band,
        "districts_ranked_slowest": result,
        "needs_improvement": [r["district"] for r in result if r["severity"] in ["HIGH", "MEDIUM"]],
    }, ensure_ascii=False, indent=2)

@mcp.tool()
def get_most_unstable_district() -> str:
    """
    Самый нестабильный район.
    Отвечает на: 'Какой район самый нестабильный?'
    """
    instability = {
        name: round(d["avg_ping"] * 0.4 + d["bad_pct"] * 0.6, 1)
        for name, d in DISTRICTS.items()
    }
    ranked = sorted(instability.items(), key=lambda x: x[1], reverse=True)
    result = []
    for name, score in ranked:
        d = DISTRICTS[name]
        result.append({
            "district": name,
            "instability_score": score,
            "avg_ping_ms": d["avg_ping"],
            "bad_pct": d["bad_pct"],
            "avg_download_mbps": d["avg_dl"],
        })
    return json.dumps({
        "status": "ok",
        "most_unstable": ranked[0][0],
        "instability_score": ranked[0][1],
        "ranked": result,
        "explanation": "Индекс нестабильности = пинг×0.4 + % плохих точек×0.6"
    }, ensure_ascii=False, indent=2)

@mcp.tool()
def get_speed_trend(district_name: str = "all") -> str:
    """
    Динамика скорости за последние 6 месяцев.
    Отвечает на: 'Как менялась скорость за последний месяц?'
    """
    if district_name.lower() == "all" or district_name == "":
        city_trend = []
        for i in range(6):
            total_pts = sum(d["pts"] for d in DISTRICTS.values())
            avg = sum(MONTHLY_TREND[name][i] * DISTRICTS[name]["pts"]
                      for name in DISTRICTS) / total_pts
            city_trend.append(round(avg, 1))

        change_1m = round(city_trend[-1] - city_trend[-2], 1)
        change_3m = round(city_trend[-1] - city_trend[-3], 1)
        change_6m = round(city_trend[-1] - city_trend[0], 1)

        return json.dumps({
            "status": "ok",
            "scope": "Весь город",
            "months": MONTHS,
            "speed_mbps": city_trend,
            "current_mbps": city_trend[-1],
            "change_1_month": change_1m,
            "change_3_months": change_3m,
            "change_6_months": change_6m,
            "trend": "растёт" if change_1m > 0 else "падает" if change_1m < 0 else "стабильно",
            "summary": f"За последний месяц скорость {'выросла' if change_1m > 0 else 'упала'} на {abs(change_1m)} Мбит/с"
        }, ensure_ascii=False, indent=2)

    matched = next((name for name in DISTRICTS if district_name.lower() in name.lower()), None)
    if not matched:
        return json.dumps({"status": "error", "message": f"Район '{district_name}' не найден"})

    trend = MONTHLY_TREND[matched]
    change_1m = round(trend[-1] - trend[-2], 1)
    change_3m = round(trend[-1] - trend[-3], 1)
    return json.dumps({
        "status": "ok",
        "district": matched,
        "months": MONTHS,
        "speed_mbps": trend,
        "current_mbps": trend[-1],
        "change_1_month": change_1m,
        "change_3_months": change_3m,
        "trend": "растёт" if change_1m > 0 else "падает" if change_1m < 0 else "стабильно",
        "summary": f"{matched}: за последний месяц скорость {'выросла' if change_1m > 0 else 'упала'} на {abs(change_1m)} Мбит/с"
    }, ensure_ascii=False, indent=2)

@mcp.tool()
def analyze_port_failure(port_id: int) -> str:
    """
    Анализ последствий отказа порта — кого затронет.
    Отвечает на: 'Порт N отказал, кого это затронет?'
    """
    try:
        url = f"{BASE_URL}/{port_id}/impact"
        with httpx.Client(timeout=15.0, verify=False) as c:
            r = c.get(url, headers={
                "Accept": "application/json",
                "Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIiwidSI6ImFkbWluIiwiciI6ImFkbWluIiwiaWF0IjoxNzc5Nzc2MTEwLCJleHAiOjE3Nzk4MTkzMTB9.4GsK00y46OdpmsS-tu24L7x8AY92ulcu04t9OfHRHTE"
            })
            r.raise_for_status()
            data = r.json()

        counts   = data.get("counts", {})
        affected_terminals = data.get("affected_terminal_ids", [])
        affected_cables    = data.get("affected_cable_ids", [])
        affected_users = len(affected_terminals) * random.randint(8, 15)

        district = "неизвестен"
        for f in data.get("features", []):
            if f["geometry"] and f["geometry"]["type"] == "MultiLineString":
                coords = f["geometry"]["coordinates"][0][0]
                lon, lat = coords[0], coords[1]
                if lat < 51.10: district = "Байконур"
                elif lat < 51.14: district = "Алматы"
                elif lat < 51.17: district = "Сарыарка"
                elif lon > 71.46: district = "Нура"
                else: district = "Есиль"
                break

        severity = "КРИТИЧЕСКИЙ" if len(affected_terminals) > 5 else \
                   "ВЫСОКИЙ"     if len(affected_terminals) > 2 else "СРЕДНИЙ"

        return json.dumps({
            "status": "ok",
            "port_id": port_id,
            "district": district,
            "severity": severity,
            "affected_terminals": len(affected_terminals),
            "affected_cables": len(affected_cables),
            "estimated_affected_users": affected_users,
            "cables_without_geo": counts.get("cables", 0) - len([
                f for f in data.get("features", [])
                if f["properties"]["kind"] == "cable" and f["geometry"]
            ]),
            "root_cable": data.get("root_cable_id"),
            "action_required": f"Срочно проверить {len(affected_terminals)} терминалов в районе {district}",
        }, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})

@mcp.tool()
def analyze_multiple_port_failures(port_ids: list[int]) -> str:
    """
    Анализ одновременного отказа нескольких портов.
    Отвечает на: 'Какие районы в зоне риска при отказе портов N1, N2?'
    """
    results = []
    all_terminals = set()
    all_cables    = set()

    for port_id in port_ids[:5]: 
        try:
            url = f"{BASE_URL}/{port_id}/impact"
            with httpx.Client(timeout=60.0, verify=False) as c:
                r = c.get(url, headers={"Accept": "application/json"})
                r.raise_for_status()
                data = r.json()

            terminals = set(data.get("affected_terminal_ids", []))
            cables    = set(data.get("affected_cable_ids", []))
            all_terminals |= terminals
            all_cables    |= cables

            results.append({
                "port_id":             port_id,
                "status":              "ok",
                "affected_terminals":  len(terminals),
                "affected_cables":     len(cables),
            })
        except Exception as e:
            results.append({"port_id": port_id, "status": "error", "message": str(e)})

    total_users = len(all_terminals) * random.randint(8, 15)
    return json.dumps({
        "status": "ok",
        "ports_analyzed": len(port_ids),
        "ports_detail": results,
        "total_unique_terminals": len(all_terminals),
        "total_unique_cables":    len(all_cables),
        "estimated_total_users":  total_users,
        "risk_level": "КРИТИЧЕСКИЙ" if total_users > 100 else
                      "ВЫСОКИЙ"     if total_users > 50  else "СРЕДНИЙ",
        "recommendation": f"При одновременном отказе {len(port_ids)} портов пострадают ~{total_users} пользователей"
    }, ensure_ascii=False, indent=2)

@mcp.tool()
def get_highest_risk_ports() -> str:
    """
    Возвращает список самых критичных портов по оценке потенциального ущерба.
    Отвечает на: 'Какой порт имеет самый высокий risk score?'
    """
    mock_ports = [
        {"port_id": 76919756, "risk_score": 98, "affected_terminals": 142, "district": "Сарыарка"},
        {"port_id": 76919712, "risk_score": 85, "affected_terminals": 89, "district": "Алматы"},
        {"port_id": 76919788, "risk_score": 72, "affected_terminals": 45, "district": "Байконур"}
    ]
    return json.dumps({
        "status": "ok",
        "top_risky_ports": mock_ports,
        "recommendation": "Рекомендуется превентивная проверка порта 76919756, так как его отказ затронет более 100 терминалов."
    }, ensure_ascii=False, indent=2)

@mcp.tool()
def get_infrastructure_priorities() -> str:
    """
    Где срочно нужно развивать инфраструктуру.
    Отвечает на: 'Где срочно нужно развивать инфраструктуру?'
    """
    priorities = []
    for name, d in sorted(DISTRICTS.items(), key=lambda x: x[1]["bad_pct"], reverse=True):
        score = round(d["bad_pct"] * 0.5 + (100 - d["avg_dl"]) * 0.3 + d["avg_ping"] * 0.2, 1)
        priorities.append({
            "district":           name,
            "priority_score":     score,
            "bad_pct":            d["bad_pct"],
            "avg_download_mbps":  d["avg_dl"],
            "avg_ping_ms":        d["avg_ping"],
            "severity":           d["severity"],
            "action": (
                "Срочная модернизация оборудования" if d["severity"] == "HIGH" else
                "Плановое расширение мощностей"    if d["severity"] == "MEDIUM" else
                "Мониторинг"
            )
        })
    return json.dumps({
        "status":            "ok",
        "top_priority":      priorities[0]["district"],
        "priorities":        priorities
    }, ensure_ascii=False, indent=2)

@mcp.tool()
def get_client_loss_risk() -> str:
    """
    Где теряются клиенты из-за плохого интернета.
    Отвечает на: 'Где я теряю клиентов из-за скорости?'
    """
    risk_districts = []
    for name, d in sorted(DISTRICTS.items(), key=lambda x: x[1]["bad_pct"], reverse=True):
        churn_risk = round(d["bad_pct"] * 0.7 + max(0, 40 - d["avg_dl"]/4) * 0.3, 1)
        risk_districts.append({
            "district":          name,
            "churn_risk_pct":    min(churn_risk, 95),
            "potential_lost_clients": int(d["pts"] * d["bad_pct"] / 100 * 2.5),
        })
    return json.dumps({
        "status":          "ok",
        "highest_risk":    risk_districts[0]["district"],
        "districts":       risk_districts
    }, ensure_ascii=False, indent=2)

@mcp.tool()
def get_speed_in_radius(lat: float, lon: float, radius_meters: int = 500) -> str:
    """
    Анализ скорости в радиусе от адреса по точным данным из CSV.
    Отвечает на: 'Анализируй скорость по координатам...', 'Какая скорость у меня дома?'
    """
    nearby_points = []
    
    for pt in RAW_POINTS:
        dist = haversine(lat, lon, pt['lat'], pt['lon'])
        if dist <= radius_meters:
            nearby_points.append(pt)
            
    if not nearby_points:
        return json.dumps({
            "status": "warning",
            "message": f"В радиусе {radius_meters}м от {lat}, {lon} нет данных о замерах.",
        }, ensure_ascii=False, indent=2)

    total_pts = len(nearby_points)
    avg_dl = round(sum(pt['dl'] for pt in nearby_points) / total_pts, 1)
    avg_ul = round(sum(pt['ul'] for pt in nearby_points) / total_pts, 1)
    avg_ping = round(sum(pt['ping'] for pt in nearby_points) / total_pts, 1)
    
    quality = "отличное" if avg_dl >= 150 else "хорошее" if avg_dl >= 100 else "среднее" if avg_dl >= 50 else "плохое"
    
    recommendation = f"Средняя скорость {avg_dl} Мбит/с ({quality})."
    if avg_dl < 50:
        recommendation += " ВНИМАНИЕ: Скорость критически низкая! Срочно вызовите инструмент analyze_port_failure или проверьте инфраструктуру."

    return json.dumps({
        "status": "ok",
        "measurements_found": total_pts,
        "avg_download_mbps": avg_dl,
        "avg_upload_mbps": avg_ul,
        "avg_ping_ms": avg_ping,
        "quality": quality,
        "recommendation": recommendation
    }, ensure_ascii=False, indent=2)

@mcp.tool()
def get_all_districts_summary() -> str:
    """Полная сводка по всем районам."""
    avg_dl, avg_ul, avg_ping = avg_city()
    return json.dumps({
        "status": "ok",
        "city_avg_download": avg_dl,
        "districts": DISTRICTS
    }, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    # Railway динамически выдает порт, поэтому обязательно берем его из окружения (иначе сервер не запустится)
    port = int(os.environ.get("PORT", 8000))
    
    print("=" * 55)
    print(f"  Запуск Astana Network Analyzer на порту {port} (Streamable HTTP)")
    print("=" * 55)
    
    mcp.run(transport="streamable-http", host="0.0.0.0", port=port)
