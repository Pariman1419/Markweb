import React from 'react';
import { useNavigate } from 'react-router-dom';
import type { ElrRow } from '../api';

interface ElrTableProps {
  rows: ElrRow[];
  total: number;
  page: number;
  runId: number;
  onPageChange: (newPage: number) => void;
  loading?: boolean;
}

export const ElrTable: React.FC<ElrTableProps> = ({
  rows,
  total,
  page,
  runId,
  onPageChange,
  loading = false,
}) => {
  const navigate = useNavigate();
  const totalPages = Math.max(Math.ceil(total / 50), 1);

  const getBadge = (result: string) => {
    switch (result) {
      case 'TRUE':
        return 'bg-emerald-50 text-emerald-700 border-emerald-200';
      case 'WARNING':
        return 'bg-amber-50 text-amber-700 border-amber-200';
      case 'ERROR':
        return 'bg-rose-50 text-rose-700 border-rose-200';
      case 'HOLD':
        return 'bg-indigo-50 text-indigo-700 border-indigo-200';
      default:
        return 'bg-slate-50 text-slate-600 border-slate-200';
    }
  };

  return (
    <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden flex flex-col">
      <div className="overflow-x-auto flex-1">
        <table className="w-full text-left border-collapse text-xs">
          <thead>
            <tr className="bg-slate-50 border-b border-slate-200 text-slate-500 font-semibold uppercase tracking-wider text-[11px]">
              <th className="py-3 px-4">ELR Number</th>
              <th className="py-3 px-4">Month</th>
              <th className="py-3 px-4">ABS File</th>
              <th className="py-3 px-4">Result</th>
              <th className="py-3 px-4 text-center">True / Total</th>
              <th className="py-3 px-4">Driver / Blocker</th>
              <th className="py-3 px-4 text-right">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {loading ? (
              <tr>
                <td colSpan={7} className="text-center py-10 text-slate-400">
                  Loading records...
                </td>
              </tr>
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={7} className="text-center py-10 text-slate-400">
                  No ELR packages found matching current filters.
                </td>
              </tr>
            ) : (
              rows.map((row) => (
                <tr
                  key={row.elr_no}
                  onClick={() => navigate(`/elr/${row.elr_no}?run=${runId}`)}
                  className="hover:bg-indigo-50/40 cursor-pointer transition-colors"
                >
                  <td className="py-3 px-4 font-mono font-bold text-slate-800">
                    {row.elr_no}
                  </td>
                  <td className="py-3 px-4 text-slate-500 font-mono">
                    {row.month}
                  </td>
                  <td className="py-3 px-4 text-slate-600 truncate max-w-[12rem]" title={row.abs_file}>
                    {row.abs_file || '—'}
                  </td>
                  <td className="py-3 px-4">
                    <span
                      className={`inline-block px-2 py-0.5 rounded text-[11px] font-bold border ${getBadge(
                        row.result
                      )}`}
                    >
                      {row.result}
                    </span>
                  </td>
                  <td className="py-3 px-4 text-center font-mono font-medium text-slate-700">
                    {row.true_lines} / {row.total_lines}
                  </td>
                  <td className="py-3 px-4 text-slate-600 truncate max-w-[15rem]" title={row.cause}>
                    {row.cause || '—'}
                  </td>
                  <td className="py-3 px-4 text-right font-medium text-indigo-600 hover:text-indigo-800">
                    Review →
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination Footer */}
      <div className="bg-slate-50 px-4 py-3 border-t border-slate-200 flex items-center justify-between text-xs text-slate-600">
        <div>
          Showing {rows.length > 0 ? (page - 1) * 50 + 1 : 0}–
          {Math.min(page * 50, total)} of <span className="font-bold">{total}</span> packages
        </div>
        <div className="flex gap-1.5">
          <button
            onClick={() => onPageChange(page - 1)}
            disabled={page <= 1}
            className="px-3 py-1 rounded border border-slate-300 bg-white text-slate-700 hover:bg-slate-100 disabled:opacity-40 disabled:cursor-not-allowed font-medium"
          >
            Previous
          </button>
          <span className="px-3 py-1 font-mono">
            {page} / {totalPages}
          </span>
          <button
            onClick={() => onPageChange(page + 1)}
            disabled={page >= totalPages}
            className="px-3 py-1 rounded border border-slate-300 bg-white text-slate-700 hover:bg-slate-100 disabled:opacity-40 disabled:cursor-not-allowed font-medium"
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
};
