import React from 'react';

interface CauseItem {
  cause: string;
  count: number;
}

interface CauseChartProps {
  errorCauses: CauseItem[];
  holdCauses: CauseItem[];
  selectedCause?: string | null;
  onSelectCause?: (cause: string | null) => void;
}

export const CauseChart: React.FC<CauseChartProps> = ({
  errorCauses,
  holdCauses,
  selectedCause,
  onSelectCause,
}) => {
  const topErrors = errorCauses.slice(0, 5);
  const topHolds = holdCauses.slice(0, 5);
  const maxVal = Math.max(...topErrors.map((e) => e.count), ...topHolds.map((h) => h.count), 1);

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm grid grid-cols-1 md:grid-cols-2 gap-6">
      {/* Error Causes */}
      <div>
        <div className="flex justify-between items-center mb-3">
          <h4 className="text-xs font-bold uppercase text-rose-800 tracking-wider flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-rose-500" /> Error Drivers
          </h4>
          <span className="text-[11px] text-slate-400">Lines</span>
        </div>
        <div className="space-y-2">
          {topErrors.length === 0 ? (
            <div className="text-xs text-slate-400 py-4 text-center">No errors</div>
          ) : (
            topErrors.map((item) => {
              const isSelected = selectedCause === item.cause;
              const widthPct = Math.max((item.count / maxVal) * 100, 4);
              return (
                <div
                  key={item.cause}
                  onClick={() => onSelectCause?.(isSelected ? null : item.cause)}
                  className={`p-1.5 rounded cursor-pointer transition-colors ${
                    isSelected ? 'bg-rose-50 ring-1 ring-rose-400' : 'hover:bg-slate-50'
                  }`}
                >
                  <div className="flex justify-between text-xs font-medium text-slate-700 mb-1">
                    <span className="truncate max-w-[80%]" title={item.cause}>
                      {item.cause}
                    </span>
                    <span className="font-mono text-rose-600">{item.count}</span>
                  </div>
                  <div className="w-full bg-slate-100 rounded-full h-1.5 overflow-hidden">
                    <div
                      style={{ width: `${widthPct}%` }}
                      className="bg-rose-500 h-1.5 rounded-full"
                    />
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* HOLD Causes */}
      <div>
        <div className="flex justify-between items-center mb-3">
          <h4 className="text-xs font-bold uppercase text-indigo-800 tracking-wider flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-indigo-500" /> HOLD Blockers
          </h4>
          <span className="text-[11px] text-slate-400">Jobs</span>
        </div>
        <div className="space-y-2">
          {topHolds.length === 0 ? (
            <div className="text-xs text-slate-400 py-4 text-center">No hold jobs</div>
          ) : (
            topHolds.map((item) => {
              const isSelected = selectedCause === item.cause;
              const widthPct = Math.max((item.count / maxVal) * 100, 4);
              return (
                <div
                  key={item.cause}
                  onClick={() => onSelectCause?.(isSelected ? null : item.cause)}
                  className={`p-1.5 rounded cursor-pointer transition-colors ${
                    isSelected ? 'bg-indigo-50 ring-1 ring-indigo-400' : 'hover:bg-slate-50'
                  }`}
                >
                  <div className="flex justify-between text-xs font-medium text-slate-700 mb-1">
                    <span className="truncate max-w-[80%]" title={item.cause}>
                      {item.cause}
                    </span>
                    <span className="font-mono text-indigo-600">{item.count}</span>
                  </div>
                  <div className="w-full bg-slate-100 rounded-full h-1.5 overflow-hidden">
                    <div
                      style={{ width: `${widthPct}%` }}
                      className="bg-indigo-500 h-1.5 rounded-full"
                    />
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
};
