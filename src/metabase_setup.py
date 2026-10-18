"""Настройка Metabase: подключение базы и дашборд по dashboard/queries.sql."""
import os
import re
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
URL = os.environ.get("MB_URL", "http://localhost:3000")
EMAIL = os.environ.get("MB_ADMIN_EMAIL", "admin@example.com")
PASSWORD = os.environ.get("MB_ADMIN_PASSWORD", "Metabase-local-1")
COLLECTION = "Воронка и удержание"

env = dict(
    line.strip().split('=', 1)
    for line in (ROOT / '.env').read_text().splitlines()
    if '=' in line and not line.startswith('#')
)

NOTES = """**Как считаются метрики**

**Активация** — первый созданный проект в течение 7 дней после завершения регистрации.

**Retention недели N** — доля когорты, создавшей проект в интервале [регистрация + 7N дней; регистрация + 7(N+1) дней). Когорта — неделя завершения регистрации, время в UTC.

**Пустые ячейки** у поздних когорт — эти недели ещё не полностью наблюдались, поэтому не показываются. Когорты меньше 100 человек исключены.

**Неделя 0** на графике по каналам не показана: это по сути активация, по каналам она почти одинакова (26–29%).

**Что видно:** главная потеря воронки — онбординг (теряем 46% зарегистрировавшихся), на android он хуже на 11 п.п. paid_social удерживается хуже всех каналов, referral — лучше. Подробности и проверка значимости — в ноутбуке и записке.

Данные синтетические, допущения описаны в README."""

PCT = {"number_style": "percent", "decimals": 2}
WEEKS = [f"w{i}" for i in range(9)]

s = requests.Session()


def api(method, path, **kw):
    r = s.request(method, f"{URL}/api{path}", **kw)
    r.raise_for_status()
    return r.json() if r.content else None


def wait_ready():
    for _ in range(150):
        try:
            if requests.get(f"{URL}/api/health", timeout=5).json().get("status") == "ok":
                return
        except requests.RequestException:
            pass
        time.sleep(2)
    raise TimeoutError("Metabase не ответил на /api/health")


def login():
    props = api("GET", "/session/properties")
    if not props["has-user-setup"]:
        api("POST", "/setup", json={
            "token": props["setup-token"],
            "user": {"email": EMAIL, "password": PASSWORD, "first_name": "Admin", "last_name": "Local"},
            "prefs": {"site_name": "Product", "site_locale": "ru", "allow_tracking": False},
        })
    s.headers["X-Metabase-Session"] = api("POST", "/session", json={"username": EMAIL, "password": PASSWORD})["id"]


def connect_db():
    name = env["POSTGRES_DB"]
    found = [d for d in api("GET", "/database")["data"] if d["name"] == name]
    if found:
        return found[0]["id"]
    return api("POST", "/database", json={
        "engine": "postgres",
        "name": name,
        "details": {
            "host": "db",
            "port": 5432,
            "dbname": name,
            "user": env["POSTGRES_USER"],
            "password": env["POSTGRES_PASSWORD"],
            "schema-filters-type": "inclusion",
            "schema-filters-patterns": "mart",
        },
    })["id"]


def reset_collection():
    found = [c for c in api("GET", "/collection") if c["name"] == COLLECTION and not c.get("archived")]
    if not found:
        return api("POST", "/collection", json={"name": COLLECTION})["id"]
    coll = found[0]["id"]
    for model in ["dashboard", "card"]:
        for item in api("GET", f"/collection/{coll}/items", params={"models": model})["data"]:
            api("DELETE", f"/{model}/{item['id']}")
    return coll


def read_queries():
    queries = {}
    for chunk in re.split(r";\s*$", (ROOT / "dashboard/queries.sql").read_text(), flags=re.M):
        lines = chunk.strip().splitlines()
        if lines:
            queries[lines[0].removeprefix("--").strip()] = "\n".join(lines[1:])
    return queries


def main():
    """Настраивает Metabase и пересоздаёт дашборд «Воронка и удержание»."""
    wait_ready()
    login()
    db = connect_db()
    coll = reset_collection()
    queries = read_queries()

    def cols(**settings):
        return {"column_settings": {f'["name","{k}"]': v for k, v in settings.items()}}

    def card(name, display, viz=None):
        return api("POST", "/card", json={
            "name": name,
            "display": display,
            "collection_id": coll,
            "visualization_settings": viz or {},
            "dataset_query": {"type": "native", "database": db, "native": {"query": queries[name]}},
        })["id"]

    def kpi(name, fmt=None):
        viz = cols(**{name: fmt}) if fmt else {}
        viz["scalar.compact_primary_number"] = False
        return card(name, "scalar", viz)

    def dashcard(card_id, row, col, w, h, **extra):
        return {"card_id": card_id, "row": row, "col": col, "size_x": w, "size_y": h, "parameter_mappings": [], **extra}

    kpis = [
        kpi("Начали регистрацию"),
        kpi("Активировались"),
        kpi("Конверсия в активацию", PCT),
        kpi("Retention недели 4", PCT),
    ]
    funnel = card("Воронка регистрации", "funnel", {
        "funnel.dimension": "step",
        "funnel.metric": "users",
        **cols(conv_first=PCT),
    })
    platforms = card("Конверсия по платформам", "bar", {
        "graph.dimensions": ["step", "platform"],
        "graph.metrics": ["conv_first"],
        "graph.x_axis.labels_enabled": False,
        "graph.y_axis.title_text": "Доля от начавших регистрацию",
        **cols(conv_first=PCT),
    })
    cohorts = card("Retention когорт по неделям", "table", {
        **cols(
            cohort_week={"column_title": "Когорта"},
            cohort_size={"column_title": "Размер"},
            **{w: {**PCT, "column_title": f"Нед. {i}"} for i, w in enumerate(WEEKS)},
        ),
        "table.column_formatting": [{
            "columns": WEEKS[1:],
            "type": "range",
            "colors": ["#FFFFFF", "#88BF4D"],
            "min_type": None,
            "max_type": None,
            "highlight_row": False,
        }],
    })
    channels = card("Retention по каналам", "line", {
        "graph.dimensions": ["week_n", "channel"],
        "graph.metrics": ["retention"],
        "graph.x_axis.scale": "ordinal",
        "graph.x_axis.title_text": "Неделя после регистрации",
        "graph.y_axis.title_text": "Retention",
        **cols(retention=PCT),
    })

    notes = {"virtual_card": {"name": None, "display": "text", "visualization_settings": {}, "dataset_query": {}, "archived": False},
             "text": NOTES}
    dashcards = [
        *[dashcard(k, 0, 6 * i, 6, 3) for i, k in enumerate(kpis)],
        dashcard(funnel, 3, 0, 12, 8),
        dashcard(platforms, 3, 12, 12, 8),
        dashcard(cohorts, 11, 0, 24, 12),
        dashcard(channels, 23, 0, 24, 8),
        dashcard(None, 31, 0, 24, 5, visualization_settings=notes),
    ]
    for i, dc in enumerate(dashcards):
        dc["id"] = -i - 1
    dash = api("POST", "/dashboard", json={"name": COLLECTION, "collection_id": coll})["id"]
    api("PUT", f"/dashboard/{dash}", json={"width": "fixed", "dashcards": dashcards})
    print(f"{URL}/dashboard/{dash}")


if __name__ == "__main__":
    main()
