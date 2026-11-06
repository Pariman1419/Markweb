import React, { useEffect, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import {
  apiFetch,
  type ElrDetailResponse,
} from '../api';
import { ActivelGrid } from '../components/ActivelGrid';
import { LineReviewForm } from '../components/LineReviewForm';
import { useEvents } from '../hooks/useEvents';

export const Preview: React.FC = () => {
  const { elr } = useParams<{ elr: string }>();
  const [searchParams] = useSearchParams();
  const runId = Number(searchParams.get('run')) || 19;
  const navigate = useNavigate();
  const eventVersion = useEvents();

  const [data, setData] = useState<ElrDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionError, setActionError] = useState<string | null>(null);
  const [blockedLines, setBlockedLines] = useState<number[]>([]);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);
  const [enlargeImage, setEnlargeImage] = useState(false);
  const [submittingApproval, setSubmittingApproval] = useState(false);

  const fetchDetail = () => {
    if (!elr) return;
    setLoading(true);
    apiFetch<ElrDetailResponse>(`/api/elrs/${elr}?run=${runId}`)
      .then((res) => {
        setData(res);
      })
      .catch((err) => {
        console.error('Failed to load detail:', err);
        setActionError(err.message || 'Failed to load ELR details');
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchDetail();
  }, [elr, runId, eventVersion]);

  const handleSaveReview = async (reviewData: {
    line_no: number;
    reason: string;
    note: string;
    corrected_mark: string;
    is_draft: boolean;
  }) => {
    setActionError(null);
    setActionSuccess(null);
    setBlockedLines([]);
    try {
      await apiFetch('/api/reviews', {
        method: 'POST',
        body: JSON.stringify({
          run_id: runId,
          elr_no: elr,
          line_no: reviewData.line_no,
          reason: reviewData.reason,
          note: reviewData.note,
          corrected_mark: reviewData.corrected_mark,
          is_draft: reviewData.is_draft,
        }),
      });
      setActionSuccess(`บันทึกรีวิวบรรทัด ${reviewData.line_no} (${reviewData.is_draft ? 'ร่าง' : 'ยืนยัน'}) เรียบร้อย`);
      fetchDetail();
    } catch (err: any) {
      setActionError(err.message || 'Failed to save review');
    }
  };

  const handleApproval = async (decision: 'APPROVED' | 'REJECTED') => {
    setActionError(null);
    setActionSuccess(null);
    setBlockedLines([]);
    setSubmittingApproval(true);

    try {
      await apiFetch('/api/approvals', {
        method: 'POST',
        body: JSON.stringify({
          run_id: runId,
          elr_no: elr,
          decision,
        }),
      });
      setActionSuccess(`บันทึกผลการตรวจสอบเป็น ${decision} เรียบร้อยแล้ว`);
      fetchDetail();
    } catch (err: any) {
      const errData = err.data || {};
      if (errData.blocked_lines) {
        setBlockedLines(errData.blocked_lines);
        setActionError(`ไม่สามารถ Approve ได้: มีบรรทัดสถานะ Error ที่ยังไม่ได้รับการรีวิวและแก้ไข (บรรทัด: ${errData.blocked_lines.join(', ')})`);
      } else if (errData.reason === 'HOLD') {
        setActionError('ไม่สามารถ Approve ได้: ELR อยู่ในสถานะ HOLD (อนุญาตเฉพาะ Reject)');
      } else {
        setActionError(err.message || `Failed to record ${decision}`);
      }
    } finally {
      setSubmittingApproval(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center text-slate-500 text-sm">
        กำลังโหลดข้อมูล ELR {elr}...
      </div>
    );
  }

  if (!data) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center text-slate-500 text-sm">
        ไม่พบข้อมูล ELR {elr} ใน Run {runId}
      </div>
    );
  }

  const { snapshot, job, lines, reviews, approval, image_available } = data;
  const isHold = job?.processing_status === 'HOLD';

  // System 5-row strings
  const systemRows = Array.from({ length: 5 }, (_, i) => {
    const line = lines.find((l) => l.line_no === i + 1);
    return line?.expected || '';
  });

  // Oracle 5-row strings
  const oracleRows = snapshot?.oracle_top_raw || ['', '', '', '', ''];

  return (
    <div className="min-h-screen bg-slate-50 text-slate-800 flex flex-col">
      {/* Header */}
      <header className="bg-white border-b border-slate-200 sticky top-0 z-20 shadow-xs px-4 py-3">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button
              onClick={() => navigate(`/?run=${runId}`)}
              className="px-2.5 py-1 text-xs border border-slate-200 rounded hover:bg-slate-100 font-medium text-slate-600"
            >
              ← กลับ Dashboard
            </button>
            <div className="border-l border-slate-200 pl-3">
              <div className="flex items-center gap-2">
                <span className="font-mono text-base font-bold text-slate-900">{elr}</span>
                <span className="text-xs text-slate-400">Run {runId}</span>
                <span
                  className={`text-[11px] font-bold px-2 py-0.5 rounded border ${
                    isHold
                      ? 'bg-indigo-50 text-indigo-700 border-indigo-200'
                      : 'bg-slate-100 text-slate-700 border-slate-200'
                  }`}
                >
                  {job?.processing_status || 'DONE'}
                </span>
                {approval && (
                  <span
                    className={`text-[11px] font-bold px-2 py-0.5 rounded border ${
                      approval.decision === 'APPROVED'
                        ? 'bg-emerald-50 text-emerald-700 border-emerald-300'
                        : 'bg-rose-50 text-rose-700 border-rose-300'
                    }`}
                  >
                    Current: {approval.decision}
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* Action Decision Buttons */}
          <div className="flex items-center gap-2">
            <button
              disabled={submittingApproval}
              onClick={() => handleApproval('REJECTED')}
              className="px-3 py-1.5 bg-rose-50 hover:bg-rose-100 text-rose-700 border border-rose-300 rounded text-xs font-bold transition-colors disabled:opacity-50"
            >
              Reject
            </button>
            <button
              disabled={submittingApproval || isHold}
              onClick={() => handleApproval('APPROVED')}
              className="px-4 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded text-xs font-bold shadow-xs transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Approve
            </button>
          </div>
        </div>
      </header>

      {/* Main Container */}
      <main className="max-w-7xl mx-auto p-4 sm:p-6 space-y-6 flex-1 w-full">
        {/* Banner Alert messages */}
        {actionError && (
          <div className="bg-rose-50 border border-rose-200 text-rose-800 text-xs p-3.5 rounded-xl flex items-start gap-2 shadow-xs">
            <span className="text-base font-bold leading-none">⚠️</span>
            <div>
              <div className="font-bold">{actionError}</div>
              {blockedLines.length > 0 && (
                <div className="mt-1 text-[11px]">
                  กรุณากรอกเหตุผลและค่ามาร์กที่ถูกต้องในฟอร์มด้านล่างสำหรับบรรทัด {blockedLines.join(', ')} แล้วกด Confirm Review ก่อนทำการ Approve
                </div>
              )}
            </div>
          </div>
        )}

        {actionSuccess && (
          <div className="bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs p-3 rounded-xl flex items-center gap-2 shadow-xs">
            <span>✅</span>
            <span className="font-medium">{actionSuccess}</span>
          </div>
        )}

        {/* If Job is HOLD, display HOLD Banner */}
        {isHold && (
          <div className="bg-indigo-50 border-2 border-indigo-300 rounded-xl p-6 text-center space-y-2">
            <div className="text-2xl">🛑</div>
            <h2 className="text-base font-bold text-indigo-900">
              ELR Package ติดสถานะ HOLD: {job?.hold_reason}
            </h2>
            {job?.hold_detail && (
              <p className="text-xs text-indigo-700 max-w-xl mx-auto font-mono bg-white/60 p-2 rounded border border-indigo-200">
                {job.hold_detail}
              </p>
            )}
            <p className="text-xs text-indigo-500">
              แพ็กเกจนี้ถูกระงับกระบวนการเปรียบเทียบชั่วคราว จึงไม่มีตาราง ACTIVEL หรือภาพเปรียบเทียบ
            </p>
          </div>
        )}

        {!isHold && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
            {/* LEFT COLUMN: System Generated & Evidence */}
            <div className="space-y-6">
              {/* ABS Image Preview */}
              <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm">
                <div className="flex justify-between items-center mb-2">
                  <h3 className="text-xs font-bold uppercase text-slate-700 tracking-wide flex items-center gap-2">
                    <span>Customer Drawing (ABS)</span>
                    {snapshot?.abs_file && (
                      <span className="font-mono text-slate-500 font-normal">({snapshot.abs_file})</span>
                    )}
                  </h3>
                  {image_available && (
                    <button
                      onClick={() => setEnlargeImage(true)}
                      className="text-xs text-indigo-600 hover:underline font-medium"
                    >
                      Click to Enlarge 🔍
                    </button>
                  )}
                </div>

                <div className="border border-slate-200 rounded-lg bg-slate-900/5 flex items-center justify-center min-h-[14rem] overflow-hidden">
                  {image_available ? (
                    <img
                      src={`/api/files/abs/${runId}/${elr}`}
                      alt="ABS Drawing"
                      loading="lazy"
                      className="max-h-72 object-contain cursor-pointer hover:scale-[1.02] transition-transform"
                      onClick={() => setEnlargeImage(true)}
                    />
                  ) : (
                    <div className="text-xs text-slate-400 py-12 text-center">
                      ไม่มีภาพ ABS (ภาพ drawing ไม่พบในแคช)
                    </div>
                  )}
                </div>
              </div>

              {/* SLR Instructions Used */}
              <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm">
                <h3 className="text-xs font-bold uppercase text-slate-700 tracking-wide mb-2">
                  Special Lot Request (SLR) Instructions
                </h3>
                {snapshot?.slr_instructions && snapshot.slr_instructions.length > 0 ? (
                  <div className="space-y-1.5">
                    {snapshot.slr_instructions.map((inst, i) => (
                      <div key={i} className="text-xs bg-slate-50 border border-slate-200 rounded p-2 font-mono">
                        <div className="flex justify-between text-slate-500 text-[10px] mb-0.5">
                          <span>Target Line: {inst.line}</span>
                          <span className="italic">Quote: "{inst.quote}"</span>
                        </div>
                        <div className="text-slate-900 font-bold">Value: {inst.value}</div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-xs text-slate-400 py-2">
                    ไม่มีคำสั่งพิเศษจาก SLR สำหรับ TOP Mark
                  </div>
                )}
              </div>

              {/* System ACTIVEL Grid */}
              <ActivelGrid
                title="System Generated ACTIVEL"
                rows={systemRows}
                other={oracleRows}
                layout={snapshot?.layout_cells}
                isSystem={true}
              />

              {/* Per-Line Rule & Provenance Metadata */}
              <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm">
                <h3 className="text-xs font-bold uppercase text-slate-700 tracking-wide mb-3">
                  Line Verification & Rule Attribution
                </h3>
                <div className="space-y-2">
                  {lines.map((l) => (
                    <div
                      key={l.line_no}
                      className="text-xs border border-slate-200 rounded p-2.5 bg-slate-50/50 flex flex-col gap-1"
                    >
                      <div className="flex justify-between items-center">
                        <span className="font-mono font-bold text-slate-800">
                          Line {l.line_no}: <span className="text-indigo-600">{l.expected || '(blank)'}</span>
                        </span>
                        <span className="text-[10px] font-mono bg-white px-2 py-0.5 rounded border border-slate-200">
                          Rule: {l.compare_rules || 'EXACT'}
                        </span>
                      </div>
                      {l.detail && (
                        <div className="text-[11px] text-slate-500 font-mono">
                          Detail: {l.detail}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* RIGHT COLUMN: Oracle Ground Truth & Line Review Forms */}
            <div className="space-y-6">
              {/* Oracle Meta Attributes */}
              <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm text-xs space-y-2">
                <div className="flex justify-between items-center border-b pb-2">
                  <span className="font-bold uppercase text-slate-700">Oracle ACTIVEL Attributes</span>
                  <span className="font-mono bg-slate-100 px-2 py-0.5 rounded text-slate-600 font-semibold">
                    MARK_ID: {snapshot?.top_mark_id ?? 'None'} • Layout: {snapshot?.layout_code ?? 'None'}
                  </span>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-[11px]">
                  <div>
                    <span className="text-slate-400 block">MARK_REMARK:</span>
                    <span className="font-mono text-slate-700">{snapshot?.mark_remark || '—'}</span>
                  </div>
                  <div>
                    <span className="text-slate-400 block">MARK_REQUIRE:</span>
                    <span className="font-mono text-slate-700">{snapshot?.mark_require || '—'}</span>
                  </div>
                  <div className="sm:col-span-2">
                    <span className="text-slate-400 block">TEMPLATE_REMARK:</span>
                    <span className="font-mono text-slate-700">{snapshot?.top_template_remark || '—'}</span>
                  </div>
                </div>
              </div>

              {/* Oracle ACTIVEL Grid */}
              <ActivelGrid
                title="Oracle Actual ACTIVEL"
                rows={oracleRows}
                other={systemRows}
                layout={snapshot?.layout_cells}
                isSystem={false}
              />

              {/* Line Review Forms */}
              <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm space-y-3">
                <div className="flex justify-between items-center">
                  <h3 className="text-xs font-bold uppercase text-slate-700 tracking-wide">
                    Line Reviews & Discrepancy Resolution
                  </h3>
                  <span className="text-[11px] text-slate-400">
                    {lines.filter((l) => l.group === 'ERROR').length} Discrepancies
                  </span>
                </div>
                <div className="space-y-3">
                  {lines.map((l) => (
                    <LineReviewForm
                      key={l.line_no}
                      line={l}
                      existingReview={reviews[l.line_no]}
                      onSave={handleSaveReview}
                    />
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}
      </main>

      {/* Enlarged Image Modal */}
      {enlargeImage && (
        <div
          onClick={() => setEnlargeImage(false)}
          className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4 cursor-pointer"
        >
          <div className="relative max-w-5xl max-h-[90vh] bg-white p-2 rounded-xl">
            <img
              src={`/api/files/abs/${runId}/${elr}`}
              alt="Enlarged ABS"
              className="max-h-[85vh] object-contain mx-auto"
            />
            <div className="text-center text-xs text-slate-500 mt-2 font-mono">
              Click anywhere to close
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
export default Preview;
