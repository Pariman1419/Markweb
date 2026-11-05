import React from 'react';

interface MonthlyItem {
  month: string;
  TRUE: number;
  WARNING: number;
  ERROR: number;
}

interface MonthlyChartProps {
  data: MonthlyItem[];
  selectedMonth?: string | null;
  onSelectMonth?: (month: string | null) => void;
}

export const MonthlyChart: React.FC<MonthlyChartProps> = ({
  data,
  selectedMonth,
  onSelectMonth,
}) => {
  const maxTotal = Math.max(
    ...data.map((d) => d.TRUE + d.WARNING + d.ERROR),
    1
  );

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm flex flex-col justify-between">
      <div className="flex justify-between items-center mb-4">
        <h3 className="text-sm font-bold text-slate-800">Monthly Verification Volume</h3>
        <div className="flex gap-3 text-xs text-slate-500 font-medium">
          <span className="flex items-center gap-1">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 inline-block" /> True
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2.5 h-2.5 rounded-full bg-amber-500 inline-block" /> Warning
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2.5 h-2.5 rounded-full bg-rose-500 inline-block" /> Error
          </span>
        </div>
      </div>

      <div className="flex items-end gap-3 h-48 pt-4 pb-1">
        {data.map((item) => {
          const total = item.TRUE + item.WARNING + item.ERROR;
          const isSelected = selectedMonth === item.month;
          const heightPct = Math.max((total / maxTotal) * 100, 4);

          const truePct = total > 0 ? (item.TRUE / total) * 100 : 0;
          const warnPct = total > 0 ? (item.WARNING / total) * 100 : 0;
          const errPct = total > 0 ? (item.ERROR / total) * 100 : 0;

          return (
            <div
              key={item.month}
              onClick={() => onSelectMonth?.(isSelected ? null : item.month)}
              className="flex-1 flex flex-col items-center cursor-pointer group"
            >
              <div className="text-[10px] text-slate-400 mb-1 group-hover:text-slate-700 font-mono">
                {total}
              </div>
              <div
                style={{ height: `${heightPct}%` }}
                className={`w-full max-w-[2.5rem] rounded-t flex flex-col-reverse overflow-hidden transition-all ${
                  isSelected ? 'ring-2 ring-indigo-500 ring-offset-1' : 'opacity-90 group-hover:opacity-100'
                }`}
              >
                <div
                  style={{ height: `${truePct}%` }}
                  className="bg-emerald-500 hover:bg-emerald-600 transition-colors"
                  title={`True: ${item.TRUE}`}
                />
                <div
                  style={{ height: `${warnPct}%` }}
                  className="bg-amber-500 hover:bg-amber-600 transition-colors"
                  title={`Warning: ${item.WARNING}`}
                />
                <div
                  style={{ height: `${errPct}%` }}
                  className="bg-rose-500 hover:bg-rose-600 transition-colors"
                  title={`Error: ${item.ERROR}`}
                />
              </div>
              <div
                className={`text-[11px] mt-2 font-mono font-medium ${
                  isSelected ? 'text-indigo-600 font-bold' : 'text-slate-500'
                }`}
              >
                {item.month.slice(5)}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
