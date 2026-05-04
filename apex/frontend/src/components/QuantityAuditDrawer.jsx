import { X } from 'lucide-react';

const SOURCE_COLORS = {
  ai: 'bg-blue-100 text-blue-800',
  manual: 'bg-gray-100 text-gray-700',
  adjusted: 'bg-amber-100 text-amber-800',
};

const STATUS_COLORS = {
  unreviewed: 'bg-yellow-100 text-yellow-800',
  confirmed: 'bg-green-100 text-green-800',
  changed: 'bg-blue-100 text-blue-800',
  obsolete: 'bg-red-100 text-red-800',
};

function Badge({ label, colorClass }) {
  return <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${colorClass}`}>{label}</span>;
}

function Section({ title, children }) {
  return (
    <div className="py-4 border-b border-gray-100 last:border-0">
      <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">{title}</h4>
      {children}
    </div>
  );
}

function Row({ label, value }) {
  return (
    <div className="flex items-start justify-between gap-2 text-sm mb-1">
      <span className="text-gray-500 shrink-0">{label}</span>
      <span className="text-gray-800 text-right">{value ?? '—'}</span>
    </div>
  );
}

export default function QuantityAuditDrawer({ open, item, onClose }) {
  if (!open || !item) return null;

  let assumptions = [];
  try { assumptions = item.assumptions_json ? JSON.parse(item.assumptions_json) : []; } catch (_) {}

  const confidencePct = item.confidence != null ? Math.round(item.confidence * 100) : null;

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 z-40 bg-black/20" onClick={onClose} />

      {/* Drawer */}
      <div className="fixed top-0 right-0 z-50 h-full w-[440px] bg-white shadow-2xl flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-gray-100 px-5 py-4 shrink-0">
          <h3 className="font-bold text-gray-800">{item.label || 'Quantity Detail'}</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-5">
          <Section title="Measurement">
            <Row label="Type" value={item.measurement_type} />
            <Row label="Quantity" value={item.quantity != null ? `${item.quantity} ${item.unit || ''}`.trim() : null} />
            {item.geometry_geojson && (
              <Row label="Geometry" value={<span className="text-xs font-mono text-gray-400 break-all">{item.geometry_geojson.slice(0, 80)}{item.geometry_geojson.length > 80 ? '…' : ''}</span>} />
            )}
          </Section>

          <Section title="Provenance">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm text-gray-500">Source method</span>
              <Badge
                label={item.source_method || 'unknown'}
                colorClass={SOURCE_COLORS[item.source_method] || 'bg-gray-100 text-gray-700'}
              />
            </div>
            {confidencePct != null && (
              <div className="mb-2">
                <div className="flex justify-between text-sm mb-1">
                  <span className="text-gray-500">Confidence</span>
                  <span className="text-gray-800 font-medium">{confidencePct}%</span>
                </div>
                <div className="w-full bg-gray-100 rounded-full h-1.5">
                  <div
                    className={`h-1.5 rounded-full ${confidencePct >= 75 ? 'bg-green-500' : confidencePct >= 40 ? 'bg-amber-400' : 'bg-red-400'}`}
                    style={{ width: `${confidencePct}%` }}
                  />
                </div>
              </div>
            )}
          </Section>

          <Section title="Review">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm text-gray-500">Status</span>
              <Badge
                label={item.review_status || 'unreviewed'}
                colorClass={STATUS_COLORS[item.review_status] || STATUS_COLORS.unreviewed}
              />
            </div>
            {item.updated_at && (
              <Row label="Last updated" value={new Date(item.updated_at).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })} />
            )}
          </Section>

          <Section title="Assumptions">
            {assumptions.length > 0 ? (
              <ul className="space-y-1">
                {assumptions.map((a, i) => (
                  <li key={i} className="text-sm text-gray-700 flex items-start gap-2">
                    <span className="text-gray-400 mt-0.5">•</span>
                    <span>{typeof a === 'string' ? a : JSON.stringify(a)}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-gray-400">None recorded</p>
            )}
          </Section>

          {item.notes && (
            <Section title="Notes">
              <p className="text-sm text-gray-700">{item.notes}</p>
            </Section>
          )}
        </div>
      </div>
    </>
  );
}
