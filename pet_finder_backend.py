import os
import time
import requests
import psycopg2
from flask import Flask, jsonify, request
from flask_cors import CORS
from psycopg2.extras import RealDictCursor

app = Flask(__name__)
CORS(app)

DATABASE_URL = os.environ.get("DATABASE_URL")
PLACE_ID = "107778070777162"
ROBLOX_API = (
    f"https://games.roblox.com/v1/games/{PLACE_ID}/servers/Public"
)


def get_conn():
    if not DATABASE_URL:
        raise RuntimeError("Falta DATABASE_URL en Render")
    return psycopg2.connect(DATABASE_URL, sslmode="require")


def init_db():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS egg_reports (
                    id BIGSERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    rarity TEXT,
                    weight DOUBLE PRECISION,
                    income DOUBLE PRECISION,
                    server_id TEXT,
                    area TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS egg_reports_created_at_idx
                ON egg_reports (created_at DESC)
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS public_servers (
                    place_id TEXT NOT NULL,
                    server_id TEXT NOT NULL,
                    playing INTEGER NOT NULL DEFAULT 0,
                    max_players INTEGER NOT NULL DEFAULT 0,
                    updated_at TIMESTAMPTZ DEFAULT NOW(),
                    PRIMARY KEY (place_id, server_id)
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS public_server_sync_state (
                    place_id TEXT PRIMARY KEY,
                    next_cursor TEXT,
                    pages_read INTEGER NOT NULL DEFAULT 0,
                    total_seen BIGINT NOT NULL DEFAULT 0,
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            cur.execute("""
                INSERT INTO public_server_sync_state (place_id)
                VALUES (%s)
                ON CONFLICT (place_id) DO NOTHING
            """, (PLACE_ID,))


@app.route("/")
def home():
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM egg_reports")
                report_count = cur.fetchone()[0]
                cur.execute("""
                    SELECT COUNT(*) FROM public_servers
                    WHERE place_id = %s
                """, (PLACE_ID,))
                server_count = cur.fetchone()[0]

        return jsonify({
            "service": "PET Finder | ZYNEX",
            "status": "online",
            "reports": report_count,
            "public_servers_saved": server_count,
            "place_id": PLACE_ID
        })
    except Exception as e:
        app.logger.exception("Home error")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/health")
def health():
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return jsonify({"ok": True, "database": "connected"})
    except Exception as e:
        return jsonify({
            "ok": False,
            "database": "error",
            "error": str(e)
        }), 500


@app.route("/reports", methods=["GET", "POST"])
def reports():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        name = data.get("name")

        if not name:
            return jsonify({
                "ok": False,
                "error": "Falta el campo name"
            }), 400

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO egg_reports
                        (name, rarity, weight, income, server_id, area)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    str(name),
                    data.get("rarity"),
                    data.get("weight", data.get("weight_kg")),
                    data.get("income", data.get("income_per_second")),
                    data.get("server_id"),
                    data.get("area")
                ))
                report_id = cur.fetchone()[0]

        return jsonify({"ok": True, "id": report_id}), 201

    rarity = request.args.get("rarity", "ALL").upper()
    limit = min(max(request.args.get("limit", 100, type=int), 1), 500)

    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if rarity == "ALL":
                cur.execute("""
                    SELECT id, name, rarity, weight,
                           weight AS weight_kg, income,
                           income AS income_per_second,
                           server_id, area, created_at
                    FROM egg_reports
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (limit,))
            else:
                cur.execute("""
                    SELECT id, name, rarity, weight,
                           weight AS weight_kg, income,
                           income AS income_per_second,
                           server_id, area, created_at
                    FROM egg_reports
                    WHERE UPPER(rarity) = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (rarity, limit))
            rows = cur.fetchall()

    return jsonify(rows)


@app.route("/servers")
def servers():
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT server_id,
                       COUNT(*) AS report_count,
                       COUNT(DISTINCT name) AS egg_types,
                       MAX(created_at) AS last_seen
                FROM egg_reports
                WHERE server_id IS NOT NULL AND server_id <> ''
                GROUP BY server_id
                ORDER BY MAX(created_at) DESC
                LIMIT 500
            """)
            rows = cur.fetchall()

    return jsonify({
        "ok": True,
        "servers_count": len(rows),
        "servers": rows
    })


@app.route("/sync-public-servers", methods=["GET", "POST"])
def sync_public_servers():
    # Cada llamada procesa solamente una página.
    # El cursor queda guardado en PostgreSQL para continuar
    # en la siguiente llamada, incluso tras reiniciar Render.
    try:
        with get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT next_cursor, pages_read, total_seen
                    FROM public_server_sync_state
                    WHERE place_id = %s
                    FOR UPDATE
                """, (PLACE_ID,))
                state = cur.fetchone()

                if state is None:
                    cur.execute("""
                        INSERT INTO public_server_sync_state (place_id)
                        VALUES (%s)
                        ON CONFLICT (place_id) DO NOTHING
                    """, (PLACE_ID,))
                    cursor_token = None
                    pages_read = 0
                    total_seen = 0
                else:
                    cursor_token = state["next_cursor"]
                    pages_read = state["pages_read"]
                    total_seen = state["total_seen"]

                params = {"sortOrder": "Desc", "limit": 100}
                if cursor_token:
                    params["cursor"] = cursor_token

                response = requests.get(
                    ROBLOX_API,
                    params=params,
                    headers={"User-Agent": "Mozilla/5.0"},
                    timeout=15
                )

                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    try:
                        retry_seconds = int(retry_after) if retry_after else 60
                    except (TypeError, ValueError):
                        retry_seconds = 60

                    return jsonify({
                        "ok": False,
                        "error": "Roblox está limitando las solicitudes",
                        "http_status": 429,
                        "retry_after_seconds": retry_seconds,
                        "pages_read": pages_read,
                        "total_seen": total_seen
                    }), 429

                if response.status_code != 200:
                    return jsonify({
                        "ok": False,
                        "error": "Roblox rechazó la solicitud",
                        "http_status": response.status_code,
                        "pages_read": pages_read,
                        "total_seen": total_seen
                    }), 502

                payload = response.json()
                server_list = payload.get("data", [])
                next_cursor = payload.get("nextPageCursor")

                saved = 0
                for server in server_list:
                    server_id = server.get("id")
                    if not server_id:
                        continue

                    cur.execute("""
                        INSERT INTO public_servers
                            (place_id, server_id, playing,
                             max_players, updated_at)
                        VALUES (%s, %s, %s, %s, NOW())
                        ON CONFLICT (place_id, server_id)
                        DO UPDATE SET
                            playing = EXCLUDED.playing,
                            max_players = EXCLUDED.max_players,
                            updated_at = NOW()
                    """, (
                        PLACE_ID,
                        server_id,
                        server.get("playing", 0),
                        server.get("maxPlayers", 0)
                    ))
                    saved += 1

                pages_read += 1
                total_seen += len(server_list)

                # Cuando termina una vuelta, la siguiente comienza
                # desde la primera página.
                if not next_cursor:
                    cur.execute("""
                        UPDATE public_server_sync_state
                        SET next_cursor = NULL,
                            pages_read = 0,
                            total_seen = 0,
                            updated_at = NOW()
                        WHERE place_id = %s
                    """, (PLACE_ID,))
                    finished = True
                else:
                    cur.execute("""
                        UPDATE public_server_sync_state
                        SET next_cursor = %s,
                            pages_read = %s,
                            total_seen = %s,
                            updated_at = NOW()
                        WHERE place_id = %s
                    """, (
                        next_cursor,
                        pages_read,
                        total_seen,
                        PLACE_ID
                    ))
                    finished = False

        return jsonify({
            "ok": True,
            "place_id": PLACE_ID,
            "pages_read_this_request": 1,
            "servers_in_this_page": len(server_list),
            "saved_or_updated": saved,
            "pages_in_cycle": pages_read if not finished else 0,
            "total_seen_in_cycle": total_seen if not finished else len(server_list),
            "more_pages": bool(next_cursor),
            "cycle_finished": finished
        })

    except requests.RequestException as e:
        app.logger.warning("Roblox request failed: %s", e)
        return jsonify({
            "ok": False,
            "error": "No se pudo conectar con Roblox",
            "details": str(e)
        }), 502
    except Exception as e:
        app.logger.exception("Public server sync failed")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/public-servers")
def public_servers():
    min_players = request.args.get("min_players", 3, type=int)
    max_players = request.args.get("max_players", 4, type=int)
    limit = min(max(request.args.get("limit", 500, type=int), 1), 1000)

    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT server_id, playing, max_players, updated_at
                FROM public_servers
                WHERE place_id = %s
                  AND playing BETWEEN %s AND %s
                ORDER BY updated_at DESC
                LIMIT %s
            """, (PLACE_ID, min_players, max_players, limit))
            rows = cur.fetchall()

    return jsonify({
        "ok": True,
        "place_id": PLACE_ID,
        "count": len(rows),
        "filter": {
            "min_players": min_players,
            "max_players": max_players
        },
        "servers": rows
    })


with app.app_context():
    init_db()


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000))
    )
    
