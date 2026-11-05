import React from 'react';
import type { StatusCard } from '../api';

interface StatusCardsProps {
  cards: {
    TRUE: StatusCard;
    WARNING: StatusCard;
    ERROR: StatusCard;
    HOLD: StatusCard;
  };
  selectedResult?: string | null;
  onSelectResult?: (result: string | null) => void;
}

export const StatusCards: React.FC<StatusCardsProps> = ({
  cards,
  selectedResult,
  onSelectResult,
}) => {
  const items = [
    {
      key: 'TRUE',
      title: 'True (Match)',
      badge: 'bg-emerald-100 text-emerald-800 border-emerald-300',
      activeRing: 'ring-2 ring-emerald-500 border-emerald-500 bg-emerald-50/40',
      data: cards.TRUE,
    },
    {
      key: 'WARNING',
      title: 'Warning (Review)',
      badge: 'bg-amber-100 text-amber-800 border-amber-300',
      activeRing: 'ring-2 ring-amber-500 border-amber-500 bg-amber-50/40',
      data: cards.WARNING,
    },
    {
      key: 'ERROR',
      title: 'Error (Diff / Empty)',
      badge: 'bg-rose-100 text-rose-800 border-rose-300',
      activeRing: 'ring-2 ring-rose-500 border-rose-500 bg-rose-50/40',
      data: cards.ERROR,
    },
    {
      key: 'HOLD',
      title: 'HOLD (Gated)',
      badge: 'bg-indigo-100 text-indigo-800 border-indigo-300',
      activeRing: 'ring-2 ring-indigo-500 border-indigo-500 bg-indigo-50/40',
      data: cards.HOLD,
    },
  ];

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {items.map((item) => {
        const isSelected = selectedResult === item.key;
        return (
          <div
            key={item.key}
            onClick={() => onSelectResult?.(isSelected ? null : item.key)}
            className={`border rounded-xl p-4 bg-white shadow-sm hover:shadow-md cursor-pointer transition-all ${
              isSelected ? item.activeRing : 'border-slate-200'
            }`}
          >
            <div className="flex justify-between items-center mb-1">
              <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
                {item.title}
              </span>
              <span className={`text-xs px-2 py-0.5 rounded-full font-bold border ${item.badge}`}>
                {item.data.pct}%
              </span>
            </div>
            <div className="text-3xl font-extrabold text-slate-800 tracking-tight my-1">
              {item.data.count.toLocaleString()}
            </div>
            <div className="text-xs text-slate-500 truncate" title={item.data.top_cause || 'No dominant cause'}>
              {item.data.top_cause ? (
                <span>
                  <strong className="text-slate-700">Top:</strong> {item.data.top_cause}
                </span>
              ) : (
                <span className="text-slate-400">100% agreement</span>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
};
