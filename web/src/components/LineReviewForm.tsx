import React, { useState } from 'react';
import type { LineDetail, ReviewItem } from '../api';

const REASON_OPTIONS = [
  { value: 'DB_WRONG', label: 'DB wrong (Oracle ACTIVEL error)' },
  { value: 'OCR_WRONG', label: 'OCR wrong (PaddleOCR / TrOCR recognition issue)' },
  { value: 'SYMBOL_WRONG', label: 'Symbol wrong (Pin1 / logo symbol defect)' },
  { value: 'SLR_ECN_CHANGE', label: 'SLR / ECN change (Customer drawing update)' },
  { value: 'RULE_MISSING', label: 'Rule missing (Engine requires new business rule)' },
  { value: 'LAYOUT_WRONG', label: 'Layout wrong (ACTIVEL cell reflow / overflow)' },
  { value: 'OTHER', label: 'Other' },
];

interface LineReviewFormProps {
  line: LineDetail;
  existingReview?: ReviewItem;
  onSave: (data: {
    line_no: number;
    reason: string;
    note: string;
    corrected_mark: string;
    is_draft: boolean;
  }) => Promise<void>;
}

export const LineReviewForm: React.FC<LineReviewFormProps> = ({
  line,
  existingReview,
  onSave,
}) => {
  const [reason, setReason] = useState(existingReview?.reason || 'DB_WRONG');
  const [note, setNote] = useState(existingReview?.note || '');
  const [correctedMark, setCorrectedMark] = useState(existingReview?.corrected_mark || line.expected || '');
  const [saving, setSaving] = useState(false);
  const [isOpen, setIsOpen] = useState(Boolean(existingReview) || line.group === 'ERROR');

  const handleSave = async (isDraft: boolean) => {
    setSaving(true);
    try {
      await onSave({
        line_no: line.line_no,
        reason,
        note,
        corrected_mark: correctedMark,
        is_draft: isDraft,
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="border border-slate-200 rounded-lg bg-white overflow-hidden text-xs">
      <div
        onClick={() => setIsOpen(!isOpen)}
        className="px-3 py-2 bg-slate-50 border-b border-slate-200 flex justify-between items-center cursor-pointer hover:bg-slate-100"
      >
        <div className="flex items-center gap-2">
          <span className="font-mono font-bold text-slate-800">Line {line.line_no}</span>
          <span
            className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
              line.group === 'TRUE'
                ? 'bg-emerald-100 text-emerald-800'
                : line.group === 'WARNING'
                ? 'bg-amber-100 text-amber-800'
                : line.group === 'ERROR'
                ? 'bg-rose-100 text-rose-800'
                : 'bg-slate-100 text-slate-700'
            }`}
          >
            {line.status}
          </span>
          {existingReview && (
            <span
              className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${
                existingReview.is_draft ? 'bg-amber-50 text-amber-700 border border-amber-300' : 'bg-blue-50 text-blue-700 border border-blue-300'
              }`}
            >
              {existingReview.is_draft ? 'Draft Review' : 'Reviewed'}
            </span>
          )}
        </div>
        <div className="text-slate-400 font-mono text-[11px]">
          {isOpen ? '▲ Collapse' : '▼ Expand'}
        </div>
      </div>

      {isOpen && (
        <div className="p-3 space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-slate-600 font-mono text-[11px]">
            <div>
              <span className="text-slate-400 block text-[10px] uppercase font-sans">System Expected:</span>
              <span className="font-bold text-slate-900 bg-slate-50 px-1.5 py-0.5 rounded border border-slate-200 inline-block w-full">
                {line.expected || '(empty)'}
              </span>
            </div>
            <div>
              <span className="text-slate-400 block text-[10px] uppercase font-sans">Oracle Actual:</span>
              <span className="font-bold text-slate-900 bg-slate-50 px-1.5 py-0.5 rounded border border-slate-200 inline-block w-full">
                {line.oracle || '(empty)'}
              </span>
            </div>
          </div>

          {line.warning && (
            <div className="text-[11px] bg-amber-50 text-amber-800 p-2 rounded border border-amber-200">
              <strong>Warning:</strong> {line.warning}
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block text-slate-600 font-medium mb-1">Review Reason</label>
              <select
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                className="w-full border border-slate-300 rounded px-2 py-1 text-xs bg-white text-slate-800 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              >
                {REASON_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-slate-600 font-medium mb-1">Corrected Mark Value</label>
              <input
                type="text"
                value={correctedMark}
                onChange={(e) => setCorrectedMark(e.target.value)}
                placeholder="Enter approved mark"
                className="w-full border border-slate-300 rounded px-2 py-1 text-xs font-mono bg-white text-slate-800 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>
          </div>

          <div>
            <label className="block text-slate-600 font-medium mb-1">Review Note</label>
            <input
              type="text"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Investigation note or reference..."
              className="w-full border border-slate-300 rounded px-2 py-1 text-xs bg-white text-slate-800 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
          </div>

          <div className="flex justify-end gap-2 pt-1">
            <button
              type="button"
              disabled={saving}
              onClick={() => handleSave(true)}
              className="px-3 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded font-medium disabled:opacity-50"
            >
              Save Draft
            </button>
            <button
              type="button"
              disabled={saving}
              onClick={() => handleSave(false)}
              className="px-3 py-1 bg-indigo-600 hover:bg-indigo-700 text-white rounded font-medium disabled:opacity-50"
            >
              Confirm Review
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
