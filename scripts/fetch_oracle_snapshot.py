"""Fetch a read-only ELR/layout snapshot into the ignored artifacts directory."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from mark_engine.adapters.env import load_env
from mark_engine.adapters.oracle_client import connect_actl, select
from mark_engine.adapters.oracle_snapshot import layout_json, rows_to_meta

ELR_FIELDS = ('ELR_NO ELR_REV IMPORT_FILE1 CUST_REQ_NO CUST_BOM_NO CUST_BOM_REVISION '
              'CUST_ASSY_LOT PRODUCT_NO PACKAGE_CODE CURRENT_STEP STATUS LAST_TRAN MARK_APPROVE '
              'MARK_NAME IMPORT_DATE TOP_MARK_ID BACK_MARK_ID TOP_MARK1 TOP_MARK2 TOP_MARK3 '
              'TOP_MARK4 TOP_MARK5 BACK_MARK1 BACK_MARK2 BACK_MARK3 BACK_MARK4 BACK_MARK5 '
              'MARK_REMARK MARK_REQUIRE TM_LASER BM_LASER').split()
QUERY = ('SELECT ' + ', '.join('e.' + field for field in ELR_FIELDS) +
         ', t.TYPE_CODE TOP_TYPE_CODE, t.LAYOUT_CODE TOP_LAYOUT_CODE,'
         ' t.OPERATION_CODE TOP_OPERATION, t.REMARK TOP_TEMPLATE_REMARK,'
         ' t.MARK_FILE_REVISION TOP_MARK_FILE_REV, b.TYPE_CODE BACK_TYPE_CODE,'
         ' b.LAYOUT_CODE BACK_LAYOUT_CODE, b.REMARK BACK_TEMPLATE_REMARK'
         ' FROM ACTLDBA.ELR e LEFT JOIN ACTLDBA.MARK_ID t ON e.TOP_MARK_ID = t.MARK_ID'
         ' LEFT JOIN ACTLDBA.MARK_ID b ON e.BACK_MARK_ID = b.MARK_ID'
         " WHERE e.CUST_CODE = 'ADI' AND e.ELR_NO LIKE :prefix")


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
