"""Fetch a read-only ELR/layout snapshot into the ignored artifacts directory."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from mark_engine.adapters.env import load_env
from mark_engine.adapters.oracle_client import connect_actl, select
from mark_engine.adapters.oracle_snapshot import (
    BASE_ELR_QUERY,
    ELR_FIELDS,
    layout_json,
    rows_to_meta,
)

QUERY = BASE_ELR_QUERY + " AND e.ELR_NO LIKE :prefix"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--elr-prefix', nargs='+', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if not all(len(p) == 7 and p.startswith('ADI26') and p[5:].isdigit() for p in args.elr_prefix):
        parser.error('prefixes must have the form ADI26MM')
    load_env()
    conn = connect_actl()
    try:
        rows = []
        counts = {}
        for prefix in args.elr_prefix:
            fetched = select(conn, QUERY, {'prefix': prefix + '%'})
            counts[prefix] = len(fetched)
            rows.extend(fetched)
        if any(count == 0 for count in counts.values()):
            raise RuntimeError(f'No ELRs for at least one prefix: {counts}')
        meta = rows_to_meta(rows)
        ids = sorted({int(row['TOP_MARK_ID']) for row in meta if row.get('TOP_MARK_ID') is not None})
        layout_rows = []
        for start in range(0, len(ids), 500):
            chunk = ids[start:start + 500]
            binds = {f'm{i}': value for i, value in enumerate(chunk)}
            query = ('SELECT MARK_ID, MARK_ROW, MARK_COLUMN, MARK_DATA FROM ACTLDBA.MARK_ID_LAYOUT '
                     'WHERE MARK_ID IN (' + ','.join(':' + name for name in binds) + ')')
            layout_rows.extend(select(conn, query, binds))
    finally:
        conn.close()
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / 'elr_meta.json').write_text(json.dumps(meta, ensure_ascii=False), encoding='utf-8')
    (args.out / 'mark_layout.json').write_text(json.dumps(layout_json(layout_rows), ensure_ascii=False), encoding='utf-8')
    info = {'fetched_at': datetime.now(timezone.utc).isoformat(), 'prefix_rows': counts,
            'elrs': len(meta), 'layout_rows': len(layout_rows), 'elr_query': QUERY}
    (args.out / 'fetch_info.json').write_text(json.dumps(info, indent=2), encoding='utf-8')
    print('ELRs:', len(meta), 'layout rows:', len(layout_rows), 'prefix counts:', counts)


if __name__ == '__main__':
    main()
