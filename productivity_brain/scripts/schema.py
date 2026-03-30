"""
Productivity Brain — Database Schema
Central SQLite database for historical concrete estimating production rates.
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'productivity.db')


def get_db(db_path=None):
    """Get a database connection."""
    path = db_path or DB_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path=None):
    """Create all tables if they don't exist."""
    conn = get_db(db_path)
    c = conn.cursor()

    # ── Projects table ──
    c.execute("""
    CREATE TABLE IF NOT EXISTS projects (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        project_name    TEXT NOT NULL,
        file_path       TEXT UNIQUE NOT NULL,
        file_hash       TEXT,
        client          TEXT,
        estimator       TEXT,
        location        TEXT,
        estimate_date   TEXT,
        export_date     TEXT,
        labor_rate_table TEXT,
        equip_rate_table TEXT,
        total_labor_hrs REAL,
        total_labor_dollars REAL,
        total_mat_dollars   REAL,
        total_equip_dollars REAL,
        total_subs_dollars  REAL,
        grand_total     REAL,
        avg_labor_rate  REAL,
        notes           TEXT,
        created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # ── Line items table (every activity row from every estimate) ──
    c.execute("""
    CREATE TABLE IF NOT EXISTS line_items (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id      INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        row_index       INTEGER,
        wbs_area        TEXT,
        description     TEXT NOT NULL,
        quantity         REAL,
        unit            TEXT,
        crew_mix        TEXT,
        prod_rate       REAL,
        prod_unit       TEXT,
        labor_hours     REAL,
        labor_unit_price REAL,
        mat_unit_price  REAL,
        equip_prod      REAL,
        equip_unit_price REAL,
        subs_unit_price REAL,
        labor_total     REAL,
        mat_total       REAL,
        equip_total     REAL,
        subs_total      REAL,
        grand_total     REAL,
        is_summary_row  INTEGER DEFAULT 0,
        created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # ── Averaged rates view (auto-computed from line items) ──
    c.execute("""
    CREATE VIEW IF NOT EXISTS v_activity_averages AS
    SELECT
        li.description,
        li.unit,
        li.crew_mix,
        li.prod_unit,
        COUNT(DISTINCT li.project_id) AS project_count,
        COUNT(li.id) AS occurrence_count,
        ROUND(AVG(li.prod_rate), 2) AS avg_prod_rate,
        ROUND(MIN(li.prod_rate), 2) AS min_prod_rate,
        ROUND(MAX(li.prod_rate), 2) AS max_prod_rate,
        ROUND(AVG(li.labor_unit_price), 2) AS avg_labor_unit_price,
        ROUND(AVG(li.mat_unit_price), 2) AS avg_mat_unit_price,
        ROUND(AVG(li.quantity), 1) AS avg_quantity
    FROM line_items li
    WHERE li.prod_rate IS NOT NULL
      AND li.prod_unit IS NOT NULL
      AND li.is_summary_row = 0
    GROUP BY li.description, li.unit, li.prod_unit
    ORDER BY li.description
    """)

    # ── Per-project rates view (for side-by-side comparison) ──
    c.execute("""
    CREATE VIEW IF NOT EXISTS v_rates_by_project AS
    SELECT
        p.project_name,
        li.wbs_area,
        li.description,
        li.unit,
        li.crew_mix,
        li.prod_rate,
        li.prod_unit,
        li.quantity,
        li.labor_unit_price,
        li.mat_unit_price,
        li.labor_hours
    FROM line_items li
    JOIN projects p ON li.project_id = p.id
    WHERE li.prod_rate IS NOT NULL
      AND li.prod_unit IS NOT NULL
      AND li.is_summary_row = 0
    ORDER BY li.description, p.project_name
    """)

    # ── Indexes for fast queries ──
    c.execute("CREATE INDEX IF NOT EXISTS idx_li_description ON line_items(description)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_li_project ON line_items(project_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_li_wbs ON line_items(wbs_area)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_li_crew ON line_items(crew_mix)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_proj_name ON projects(project_name)")

    conn.commit()
    conn.close()
    p = db_path or DB_PATH
    print(f"Database initialized at: {os.path.abspath(p)}")


if __name__ == '__main__':
    init_db()
