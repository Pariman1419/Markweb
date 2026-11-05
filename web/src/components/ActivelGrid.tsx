import React from 'react';

interface ActivelGridProps {
  title: string;
  rows: string[]; // up to 5 strings
  other: string[]; // opposite side's 5 strings
  layout?: (string | null)[][] | null; // 5x18 layout grid
  isSystem?: boolean;
}

const COL_HEADERS = ['A', 'B', 'C', ...Array.from({ length: 18 }, (_, i) => String(i + 1))];

export const ActivelGrid: React.FC<ActivelGridProps> = ({
  title,
  rows,
  other,
  layout,
  isSystem = false,
}) => {
  // Normalize each row to 21 characters
  const formattedRows = Array.from({ length: 5 }, (_, rIdx) => {
    const raw = rows[rIdx] || '';
    if (isSystem) {
      // System: A-C blank (3 spaces), then 1-18 from expected mark
      const content = raw.padEnd(18, ' ').slice(0, 18);
      return '   ' + content;
    } else {
      // Oracle: raw chars 1-21
      return raw.padEnd(21, ' ').slice(0, 21);
    }
  });

  const formattedOther = Array.from({ length: 5 }, (_, rIdx) => {
    const raw = other[rIdx] || '';
    if (!isSystem) {
      // Other is system: A-C blank, then 1-18
      const content = raw.padEnd(18, ' ').slice(0, 18);
      return '   ' + content;
    } else {
      // Other is Oracle: raw chars 1-21
      return raw.padEnd(21, ' ').slice(0, 21);
    }
  });

  return (
    <div className="border border-slate-300 rounded-lg bg-white p-3 shadow-sm">
      <div className="text-xs font-semibold text-slate-700 mb-2 uppercase tracking-wide flex justify-between">
        <span>{title}</span>
        <span className="text-slate-400 font-normal">21 Columns × 5 Rows</span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse font-mono text-xs select-none">
          <thead>
            <tr>
              <th className="w-8 border border-slate-200 bg-slate-50 text-slate-400 font-normal py-0.5">#</th>
              {COL_HEADERS.map((h, i) => (
                <th
                  key={i}
                  className={`border border-slate-200 text-center font-semibold py-0.5 px-0.5 ${
                    i < 3 ? 'bg-amber-50 text-amber-800' : 'bg-slate-50 text-slate-600'
                  }`}
                  style={{ minWidth: '1.25rem' }}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {formattedRows.map((rowStr, rIdx) => {
              const otherStr = formattedOther[rIdx] || '';
              return (
                <tr key={rIdx}>
                  <td className="border border-slate-200 bg-slate-50 text-center text-slate-400 font-normal">
                    {rIdx + 1}
                  </td>
                  {COL_HEADERS.map((_, cIdx) => {
                    const char = rowStr[cIdx] || ' ';
                    const otherChar = otherStr[cIdx] || ' ';
                    const layoutChar =
                      layout && cIdx >= 3 && layout[rIdx] ? layout[rIdx][cIdx - 3] : null;

                    // Color logic:
                    // 1. Red if differs from other (checked first)
                    // Note: ignore difference if both are blank spaces
                    const isDiff = char !== otherChar && !(char === ' ' && otherChar === ' ');
                    // 2. Blue if reserved by layout (non-null and blank ' ' in layout)
                    const isReserved = layoutChar === ' ';

                    let cellBg = 'bg-white text-slate-800';
                    let borderClass = 'border-slate-200';

                    if (isDiff) {
                      cellBg = 'bg-rose-100 text-rose-900 font-bold';
                      borderClass = 'border-rose-300';
                    } else if (isReserved) {
                      cellBg = 'bg-sky-50 text-sky-800 font-medium';
                      borderClass = 'border-sky-200';
                    }

                    return (
                      <td
                        key={cIdx}
                        className={`border ${borderClass} ${cellBg} text-center h-6 w-5 p-0`}
                        title={`R${rIdx + 1}C${cIdx + 1} ('${char === ' ' ? 'SPACE' : char}')`}
                      >
                        {char === ' ' ? '\u00A0' : char}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};
