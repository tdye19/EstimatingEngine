/**
 * WorkScopesTab — renders Agent 2B (Work Scope Parser) output for a project.
 *
 * API schema from GET /api/projects/{id}/work-categories (WorkCategory model):
 *   wc_number            String   — e.g. "1", "28A"
 *   title                String   — short scope title
 *   work_included_items  String[] — inclusion bullets
 *   work_category_notes  String?  — prose notes block
 *   specific_notes       String[] — detail bullets
 *   related_work_by_others String[] — exclusion boundaries
 *   add_alternates       {description, price_type}[]
 *   allowances           {description, amount_dollars}[]
 *   unit_prices          {description, unit, rate}[]
 *   referenced_spec_sections String[] — CSI codes e.g. ["031000"]
 *   source_page_start    Int?
 *   source_page_end      Int?
 *   parse_method         "llm" | "regex" | "manual" | null
 *   parse_confidence     Float? (0.0–1.0)
 */

import { Fragment, useEffect, useState } from 'react';
import { ChevronDown, ChevronRight, Clipboard } from 'lucide-react';
import { getWorkCategories, listDocuments } from '../../api';

const PARSE_METHOD_COLORS = {
  llm:    'bg-purple-100 text-purple-700',
  regex:  'bg-blue-100 text-blue-700',
  manual: 'bg-gray-100 text-gray-600',
};

export default function WorkScopesTab({ projectId }) {
  const [scopes, setScopes]         = useState([]);
  const [hasWsDoc, setHasWsDoc]     = useState(null); // null = unknown, true/false after load
  const [loading, setLoading]       = useState(true);
  const [error, setError]           = useState('');
  const [expanded, setExpanded]     = useState({});

  const load = () => {
    setLoading(true);
    setError('');
    Promise.all([
      getWorkCategories(projectId),
      listDocuments(projectId),
    ])
      .then(([wcs, docs]) => {
        setScopes(wcs || []);
        const ws = (docs || []).some((d) => d.classification === 'work_scope');
        setHasWsDoc(ws);
      })
      .catch((err) => setError(err.message || 'Failed to load work scopes'))
      .finally(() => setLoading(false));
  };

  useEffect(load, [projectId]);

  const toggle = (id) => setExpanded((prev) => ({ ...prev, [id]: !prev[id] }));

  if (loading) return <div className="text-gray-400 py-8 text-center">Loading work scopes...</div>;

  if (error) return (
    <div className="text-red-500 py-8 text-center">
      {error}
      <button onClick={load} className="ml-3 text-sm underline">Retry</button>
    </div>
  );

  if (!scopes.length) {
    return (
      <div className="text-gray-400 py-8 text-center">
        {hasWsDoc
          ? 'Work Scopes document detected but no scopes parsed yet. Try re-running the pipeline.'
          : 'No Work Scopes document uploaded. Upload a Work Scopes PDF in the Documents tab and run the pipeline.'}
      </div>
    );
  }

  const fmtPages = (wc) => {
    if (wc.source_page_start == null) return '—';
    if (wc.source_page_end == null || wc.source_page_end === wc.source_page_start)
      return String(wc.source_page_start);
    return `${wc.source_page_start}–${wc.source_page_end}`;
  };

  const fmtConf = (v) => (v != null ? `${Math.round(v * 100)}%` : '—');

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex items-center gap-2 text-sm text-gray-500">
        <Clipboard className="h-4 w-4" />
        <span>{scopes.length} work scope{scopes.length !== 1 ? 's' : ''} parsed</span>
      </div>

      {/* Table card */}
      <div className="card p-0 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-gray-400 uppercase tracking-wider border-b border-gray-100 bg-gray-50">
              <th className="px-4 py-2 w-8" />
              <th className="px-4 py-2 w-16">WC #</th>
              <th className="px-4 py-2">Title</th>
              <th className="px-4 py-2 w-20">Pages</th>
              <th className="px-4 py-2 w-24">Method</th>
              <th className="px-4 py-2 w-20">Confidence</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {scopes.map((wc) => (
              <Fragment key={wc.id}>
                <tr
                  className="hover:bg-gray-50 cursor-pointer"
                  onClick={() => toggle(wc.id)}
                >
                  <td className="px-4 py-3 text-gray-400">
                    {expanded[wc.id]
                      ? <ChevronDown className="h-4 w-4" />
                      : <ChevronRight className="h-4 w-4" />}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-gray-600">{wc.wc_number}</td>
                  <td className="px-4 py-3 font-medium">{wc.title}</td>
                  <td className="px-4 py-3 text-gray-400 text-xs">{fmtPages(wc)}</td>
                  <td className="px-4 py-3">
                    {wc.parse_method ? (
                      <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${PARSE_METHOD_COLORS[wc.parse_method] || 'bg-gray-100 text-gray-500'}`}>
                        {wc.parse_method}
                      </span>
                    ) : '—'}
                  </td>
                  <td className="px-4 py-3 text-gray-500 text-xs">{fmtConf(wc.parse_confidence)}</td>
                </tr>

                {expanded[wc.id] && (
                  <tr key={`${wc.id}-detail`} className="bg-blue-50">
                    <td colSpan={6} className="px-6 py-4">
                      <div className="space-y-3">

                        {wc.work_included_items?.length > 0 && (
                          <div>
                            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">Work Included</p>
                            <ul className="list-disc list-inside space-y-0.5">
                              {wc.work_included_items.map((item, i) => (
                                <li key={i} className="text-sm text-gray-700">{item}</li>
                              ))}
                            </ul>
                          </div>
                        )}

                        {wc.work_category_notes && (
                          <div>
                            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">Notes</p>
                            <p className="text-sm text-gray-700 leading-relaxed">{wc.work_category_notes}</p>
                          </div>
                        )}

                        {wc.specific_notes?.length > 0 && (
                          <div>
                            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">Specific Notes</p>
                            <ul className="list-disc list-inside space-y-0.5">
                              {wc.specific_notes.map((note, i) => (
                                <li key={i} className="text-sm text-gray-700">{note}</li>
                              ))}
                            </ul>
                          </div>
                        )}

                        {wc.related_work_by_others?.length > 0 && (
                          <div>
                            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">Related Work by Others (Exclusions)</p>
                            <ul className="list-disc list-inside space-y-0.5">
                              {wc.related_work_by_others.map((item, i) => (
                                <li key={i} className="text-sm text-amber-700">{item}</li>
                              ))}
                            </ul>
                          </div>
                        )}

                        {wc.referenced_spec_sections?.length > 0 && (
                          <div>
                            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">Referenced Spec Sections</p>
                            <div className="flex flex-wrap gap-1.5">
                              {wc.referenced_spec_sections.map((sec, i) => (
                                <span key={i} className="bg-white border border-gray-200 rounded px-2 py-0.5 text-xs font-mono text-gray-600">{sec}</span>
                              ))}
                            </div>
                          </div>
                        )}

                        {wc.add_alternates?.length > 0 && (
                          <div>
                            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">Add Alternates</p>
                            <ul className="list-disc list-inside space-y-0.5">
                              {wc.add_alternates.map((alt, i) => (
                                <li key={i} className="text-sm text-gray-700">
                                  {alt.description}
                                  {alt.price_type && alt.price_type !== 'unknown' && (
                                    <span className="ml-1 text-xs text-gray-400">({alt.price_type})</span>
                                  )}
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}

                        {wc.allowances?.length > 0 && (
                          <div>
                            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">Allowances</p>
                            <ul className="list-disc list-inside space-y-0.5">
                              {wc.allowances.map((a, i) => (
                                <li key={i} className="text-sm text-gray-700">
                                  {a.description}
                                  {a.amount_dollars != null && (
                                    <span className="ml-1 text-gray-500">(${Number(a.amount_dollars).toLocaleString()})</span>
                                  )}
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}

                        {wc.unit_prices?.length > 0 && (
                          <div>
                            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">Unit Prices</p>
                            <ul className="list-disc list-inside space-y-0.5">
                              {wc.unit_prices.map((up, i) => (
                                <li key={i} className="text-sm text-gray-700">
                                  {up.description}
                                  {up.unit && <span className="text-gray-500"> / {up.unit}</span>}
                                  {up.rate != null && <span className="text-gray-500"> @ ${up.rate}</span>}
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}

                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
