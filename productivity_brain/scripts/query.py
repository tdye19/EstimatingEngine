"""
Productivity Brain — Query Utilities
Pull averaged rates, compare estimates, and generate reports from the database.

Usage:
    python query.py --activity "Wall Formwork"
    python query.py --activity "Continuous Footing" --fuzzy
    python query.py --crew "Formwork"
    python query.py --wbs "Heater"
    python query.py --all
    python query.py --export rates.xlsx
"""

import sqlite3
import os
import sys
import argparse
from schema import get_db, DB_PATH


def search_activities(conn, search_term=None, crew_filter=None, wbs_filter=None, fuzzy=True):
    """Search for activity averages matching filters."""
    query = """
        SELECT
            li.description,
            li.unit,
            li.crew_mix,
            li.prod_unit,
            COUNT(DISTINCT li.project_id) AS project_count,
            COUNT(li.id) AS occurrences,
            ROUND(AVG(li.prod_rate), 2) AS avg_rate,
            ROUND(MIN(li.prod_rate), 2) AS min_rate,
            ROUND(MAX(li.prod_rate), 2) AS max_rate,
            ROUND(AVG(li.labor_unit_price), 2) AS avg_lup,
            ROUND(AVG(li.mat_unit_price), 2) AS avg_mup
        FROM line_items li
        WHERE li.prod_rate IS NOT NULL
          AND li.prod_unit IS NOT NULL
          AND li.is_summary_row = 0
    """
    params = []

    if search_term:
        if fuzzy:
            query += " AND li.description LIKE ?"
            params.append(f"%{search_term}%")
        else:
            query += " AND li.description = ?"
            params.append(search_term)

    if crew_filter:
        query += " AND li.crew_mix LIKE ?"
        params.append(f"%{crew_filter}%")

    if wbs_filter:
        query += " AND li.wbs_area LIKE ?"
        params.append(f"%{wbs_filter}%")

    query += " GROUP BY li.description, li.unit, li.prod_unit ORDER BY li.description"

    return conn.execute(query, params).fetchall()


def get_activity_detail(conn, description):
    """Get per-project breakdown for a specific activity."""
    return conn.execute("""
        SELECT
            p.project_name,
            li.wbs_area,
            li.quantity,
            li.unit,
            li.prod_rate,
            li.prod_unit,
            li.crew_mix,
            li.labor_hours,
            li.labor_unit_price,
            li.mat_unit_price
        FROM line_items li
        JOIN projects p ON li.project_id = p.id
        WHERE li.description = ?
          AND li.prod_rate IS NOT NULL
          AND li.is_summary_row = 0
        ORDER BY p.project_name
    """, (description,)).fetchall()


def compare_estimate(conn, filepath):
    """Compare a new estimate file against the database averages.
    Returns list of (row_idx, desc, current_rate, hist_avg, delta_pct, hist_count, action)."""
    import pandas as pd
    from ingest import detect_format, safe_float, safe_str

    df = pd.read_excel(filepath, header=None)
    fmt = detect_format(df)
    if fmt is None:
        print("ERROR: Unknown file format")
        return []

    cols = fmt['cols']
    results = []

    for idx in range(4, len(df)):
        row = df.iloc[idx]
        desc = safe_str(row[cols['desc']])
        prod = safe_float(row[cols['prod']])
        prod_unit = safe_str(row[cols['prod_unit']])

        if desc is None or prod is None or prod_unit is None:
            continue

        # Look up historical average
        hist = conn.execute("""
            SELECT
                ROUND(AVG(prod_rate), 2) AS avg_rate,
                COUNT(*) AS cnt,
                ROUND(MIN(prod_rate), 2) AS min_rate,
                ROUND(MAX(prod_rate), 2) AS max_rate
            FROM line_items
            WHERE description = ?
              AND prod_rate IS NOT NULL
              AND is_summary_row = 0
        """, (desc,)).fetchone()

        if hist and hist['cnt'] > 0:
            avg_rate = hist['avg_rate']
            delta_pct = ((avg_rate - prod) / prod * 100) if prod != 0 else 0

            if abs(delta_pct) < 5:
                action = 'OK'
            elif abs(delta_pct) < 20:
                action = 'REVIEW'
            else:
                action = 'UPDATE'

            results.append({
                'row': idx,
                'wbs': safe_str(row[cols['wbs']]) or '',
                'description': desc,
                'quantity': safe_float(row[cols['qty']]),
                'unit': safe_str(row[cols['unit']]) or '',
                'crew': safe_str(row[cols['crew']]) or '',
                'current_rate': prod,
                'hist_avg': avg_rate,
                'hist_count': hist['cnt'],
                'hist_min': hist['min_rate'],
                'hist_max': hist['max_rate'],
                'delta_pct': round(delta_pct, 1),
                'action': action,
            })
        else:
            results.append({
                'row': idx,
                'wbs': safe_str(row[cols['wbs']]) or '',
                'description': desc,
                'quantity': safe_float(row[cols['qty']]),
                'unit': safe_str(row[cols['unit']]) or '',
                'crew': safe_str(row[cols['crew']]) or '',
                'current_rate': prod,
                'hist_avg': None,
                'hist_count': 0,
                'hist_min': None,
                'hist_max': None,
                'delta_pct': None,
                'action': 'NO DATA',
            })

    return results


def export_all_averages(conn, output_path):
    """Export all averaged rates to an Excel file."""
    import pandas as pd

    rows = search_activities(conn)
    data = [{
        'Activity': r['description'],
        'Unit': r['unit'],
        'Prod Unit': r['prod_unit'],
        'Crew': r['crew_mix'],
        'Avg Rate': r['avg_rate'],
        'Min Rate': r['min_rate'],
        'Max Rate': r['max_rate'],
        'Projects': r['project_count'],
        'Occurrences': r['occurrences'],
        'Avg Labor $/Unit': r['avg_lup'],
        'Avg Mat $/Unit': r['avg_mup'],
    } for r in rows]

    df = pd.DataFrame(data)
    df.to_excel(output_path, index=False, sheet_name='Averaged Rates')
    print(f"Exported {len(data)} averaged rates to {output_path}")


def print_results(rows):
    """Pretty-print query results."""
    if not rows:
        print("  No results found.")
        return

    print(f"\n  {'Activity':<45s} {'Unit':<6s} {'Avg Rate':>9s} {'Min':>8s} {'Max':>8s} {'#Proj':>6s} {'Crew'}")
    print(f"  {'─'*45} {'─'*6} {'─'*9} {'─'*8} {'─'*8} {'─'*6} {'─'*25}")

    for r in rows:
        crew = (r['crew_mix'] or '')[:25]
        print(f"  {r['description'][:45]:<45s} {(r['unit'] or ''):<6s} {r['avg_rate']:>9.2f} {r['min_rate']:>8.2f} {r['max_rate']:>8.2f} {r['project_count']:>6d} {crew}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Query Productivity Brain')
    parser.add_argument('--activity', '-a', help='Search by activity name')
    parser.add_argument('--crew', '-c', help='Filter by crew name')
    parser.add_argument('--wbs', '-w', help='Filter by WBS area')
    parser.add_argument('--fuzzy', action='store_true', default=True, help='Fuzzy search (default)')
    parser.add_argument('--exact', action='store_true', help='Exact match only')
    parser.add_argument('--detail', '-d', help='Show per-project detail for an activity')
    parser.add_argument('--compare', help='Compare a new estimate file against database')
    parser.add_argument('--export', help='Export all averages to Excel file')
    parser.add_argument('--all', action='store_true', help='Show all averaged rates')
    parser.add_argument('--db', default=None, help='Custom database path')

    args = parser.parse_args()
    conn = get_db(args.db)

    if args.export:
        export_all_averages(conn, args.export)
    elif args.detail:
        rows = get_activity_detail(conn, args.detail)
        if rows:
            print(f"\n  Detail for: {args.detail}")
            print(f"  {'Project':<30s} {'WBS':<25s} {'Qty':>8s} {'Rate':>8s} {'Hrs':>6s} {'L$/U':>8s}")
            print(f"  {'─'*30} {'─'*25} {'─'*8} {'─'*8} {'─'*6} {'─'*8}")
            for r in rows:
                qty = f"{r['quantity']:.1f}" if r['quantity'] else '—'
                hrs = f"{r['labor_hours']:.0f}" if r['labor_hours'] else '—'
                lup = f"${r['labor_unit_price']:.2f}" if r['labor_unit_price'] else '—'
                print(f"  {r['project_name'][:30]:<30s} {(r['wbs_area'] or '')[:25]:<25s} {qty:>8s} {r['prod_rate']:>8.2f} {hrs:>6s} {lup:>8s}")
        else:
            print(f"  No data found for: {args.detail}")
    elif args.compare:
        results = compare_estimate(conn, args.compare)
        updates = [r for r in results if r['action'] in ('REVIEW', 'UPDATE')]
        print(f"\n  {len(results)} activities analyzed, {len(updates)} flagged for review/update")
        for r in updates:
            print(f"  Row {r['row']:3d} | {r['description'][:40]:<40s} | Curr: {r['current_rate']:>8.2f} | Hist: {r['hist_avg']:>8.2f} | {r['delta_pct']:>+7.1f}% | {r['action']}")
    elif args.all:
        rows = search_activities(conn)
        print_results(rows)
    elif args.activity or args.crew or args.wbs:
        fuzzy = not args.exact
        rows = search_activities(conn, search_term=args.activity, crew_filter=args.crew, wbs_filter=args.wbs, fuzzy=fuzzy)
        print_results(rows)
    else:
        parser.print_help()

    conn.close()
