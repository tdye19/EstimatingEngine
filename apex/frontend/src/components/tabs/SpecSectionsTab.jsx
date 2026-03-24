import { useEffect, useState } from 'react';
import { getSpecSections } from '../../api';
import { ChevronDown, ChevronRight, BookOpen } from 'lucide-react';

const DIVISION_LABELS = {
  '01': 'General Requirements',
  '02': 'Existing Conditions',
  '03': 'Concrete',
  '04': 'Masonry',
  '05': 'Metals',
  '06': 'Wood, Plastics & Composites',
  '07': 'Thermal & Moisture Protection',
  '08': 'Openings',
  '09': 'Finishes',
  '10': 'Specialties',
  '11': 'Equipment',
  '12': 'Furnishings',
  '13': 'Special Construction',
  '14': 'Conveying Equipment',
  '21': 'Fire Suppression',
  '22': 'Plumbing',
  '23': 'HVAC',
  '26': 'Electrical',
  '27': 'Communications',
  '28': 'Electronic Safety & Security',
  '31': 'Earthwork',
  '32': 'Exterior Improvements',
  '33': 'Utilities',
};

const STATUS_COLORS = {
  parsed: 'bg-green-100 text-green-700',
  pending: 'bg-yellow-100 text-yellow-700',
  error: 'bg-red-100 text-red-700',
};

export default function SpecSectionsTab({ projectId }) {
  const [sections, setSections] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState({});
  const [sortBy, setSortBy] = useState('division');

  useEffect(() => {
    getSpecSections(projectId)
      .then((data) => setSections(data || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [projectId]);

  if (loading) return <div className="text-gray-400 py-8 text-center">Loading spec sections...</div>;
  if (!sections.length) return <div className="text-gray-400 py-8 text-center">No spec sections found. Run the agent pipeline to parse specification documents.</div>;

  const toggleExpand = (id) =>
    setExpanded((prev) => ({ ...prev, [id]: !prev[id] }));

  const sorted = [...sections].sort((a, b) => {
    if (sortBy === 'division') return a.section_number.localeCompare(b.section_number);
    if (sortBy === 'title') return a.title.localeCompare(b.title);
    return 0;
  });

  // Group by division
  const grouped = {};
  sorted.forEach((s) => {
    const div = s.division_number || '00';
    if (!grouped[div]) grouped[div] = [];
    grouped[div].push(s);
  });

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm text-gray-500">
          <BookOpen className="h-4 w-4" />
          <span>{sections.length} spec sections parsed</span>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-sm text-gray-500">Sort by:</label>
          <select
            className="input text-sm py-1"
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value)}
          >
            <option value="division">CSI Division</option>
            <option value="title">Title</option>
          </select>
        </div>
      </div>

      {/* Groups */}
      {Object.keys(grouped).sort().map((div) => (
        <div key={div} className="card p-0 overflow-hidden">
          {/* Division header */}
          <div className="px-4 py-2.5 bg-gray-50 border-b border-gray-200">
            <span className="text-xs font-mono font-semibold text-gray-500 uppercase tracking-wider">
              Division {div} — {DIVISION_LABELS[div] || 'Other'}
            </span>
            <span className="ml-2 text-xs text-gray-400">({grouped[div].length} sections)</span>
          </div>

          {/* Section rows */}
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-gray-400 uppercase tracking-wider border-b border-gray-100">
                <th className="px-4 py-2 w-8"></th>
                <th className="px-4 py-2 w-28">Section #</th>
                <th className="px-4 py-2 w-16">Division</th>
                <th className="px-4 py-2">Title</th>
                <th className="px-4 py-2 w-24">Status</th>
                <th className="px-4 py-2 w-24">Pages</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {grouped[div].map((s) => (
                <>
                  <tr
                    key={s.id}
                    className="hover:bg-gray-50 cursor-pointer"
                    onClick={() => toggleExpand(s.id)}
                  >
                    <td className="px-4 py-3 text-gray-400">
                      {expanded[s.id]
                        ? <ChevronDown className="h-4 w-4" />
                        : <ChevronRight className="h-4 w-4" />}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-gray-600">{s.section_number}</td>
                    <td className="px-4 py-3 text-gray-500">{s.division_number}</td>
                    <td className="px-4 py-3 font-medium">{s.title}</td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${STATUS_COLORS[s.status] || STATUS_COLORS.parsed}`}>
                        {s.status || 'parsed'}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-400 text-xs">{s.page_reference || '—'}</td>
                  </tr>
                  {expanded[s.id] && (
                    <tr key={`${s.id}-detail`} className="bg-blue-50">
                      <td colSpan={6} className="px-6 py-4">
                        <div className="space-y-3">
                          {s.content && (
                            <div>
                              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">Work Description</p>
                              <p className="text-sm text-gray-700 leading-relaxed">{s.work_description || s.content}</p>
                            </div>
                          )}
                          {s.materials_referenced?.length > 0 && (
                            <div>
                              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">Standards & Materials</p>
                              <div className="flex flex-wrap gap-1.5">
                                {s.materials_referenced.map((m, i) => (
                                  <span key={i} className="bg-white border border-gray-200 rounded px-2 py-0.5 text-xs font-mono text-gray-600">{m}</span>
                                ))}
                              </div>
                            </div>
                          )}
                          {s.submittal_requirements && (
                            <div>
                              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">Submittals</p>
                              <p className="text-sm text-gray-700">{s.submittal_requirements}</p>
                            </div>
                          )}
                          {s.keywords?.length > 0 && (
                            <div>
                              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">Keywords</p>
                              <div className="flex flex-wrap gap-1.5">
                                {s.keywords.map((k, i) => (
                                  <span key={i} className="bg-gray-100 rounded px-2 py-0.5 text-xs text-gray-500">{k}</span>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  );
}
