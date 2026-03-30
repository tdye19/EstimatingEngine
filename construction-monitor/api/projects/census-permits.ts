// ============================================================
// api/projects/census-permits.ts
// Census Building Permits Survey — MSA-Level Edge Function
//
// Data sourced from:
//   U.S. Census Bureau Building Permits Survey
//   https://api.census.gov/data/timeseries/bps/metro
//   No API key required
//
// Variables fetched:
//   BLDGS  → Total buildings authorized
//   UNITS  → Total housing units authorized
// (Permit valuation is proxied via unit-count YoY change since
//  the monthly timeseries endpoint does not expose valuation.)
//
// Covers all 12 monitored MSAs. Results are cached 4 hours in
// Upstash Redis (permits data releases monthly with a ~2-month lag).
// ============================================================

import type { EdgeResponse, SignalItem } from '../../src/types/index.ts';

// ---- MSA → Census CBSA code mapping ----
// CBSA = Core-Based Statistical Area (5-digit code used by Census)
export const MSA_CBSA_MAP: Record<string, { cbsa: string; name: string; state: string }> = {
  'phoenix':       { cbsa: '38060', name: 'Phoenix-Mesa-Chandler, AZ',                      state: 'AZ' },
  'nashville':     { cbsa: '34980', name: 'Nashville-Davidson--Murfreesboro--Franklin, TN',  state: 'TN' },
  'seattle':       { cbsa: '42660', name: 'Seattle-Tacoma-Bellevue, WA',                     state: 'WA' },
  'dallas':        { cbsa: '19100', name: 'Dallas-Fort Worth-Arlington, TX',                 state: 'TX' },
  'detroit':       { cbsa: '19820', name: 'Detroit-Warren-Dearborn, MI',                     state: 'MI' },
  'chicago':       { cbsa: '16980', name: 'Chicago-Naperville-Elgin, IL-IN-WI',              state: 'IL' },
  'columbus':      { cbsa: '18140', name: 'Columbus, OH',                                    state: 'OH' },
  'indianapolis':  { cbsa: '26900', name: 'Indianapolis-Carmel-Anderson, IN',                state: 'IN' },
  'grand-rapids':  { cbsa: '24340', name: 'Grand Rapids-Kentwood, MI',                       state: 'MI' },
  'houston':       { cbsa: '26420', name: 'Houston-The Woodlands-Sugar Land, TX',            state: 'TX' },
  'denver':        { cbsa: '19740', name: 'Denver-Aurora-Lakewood, CO',                      state: 'CO' },
  'atlanta':       { cbsa: '12060', name: 'Atlanta-Sandy Springs-Alpharetta, GA',            state: 'GA' },
};

// Reverse map: cbsa → msaId for fast lookup
const CBSA_TO_MSA_ID: Record<string, string> = Object.fromEntries(
  Object.entries(MSA_CBSA_MAP).map(([msaId, { cbsa }]) => [cbsa, msaId])
);

// ---- Census API response row types ----
// Census returns data as array-of-arrays: [header-row, ...data-rows]
// Header: ["BLDGS", "UNITS", "metropolitan statistical area", "time"]
type CensusRow = [string, string, string, string];

interface CensusApiResponse {
  header: string[];
  rows: CensusRow[];
}

// ---- Per-MSA permit metrics for downstream use ----
export interface MSAPermitData {
  msaId: string;
  msaName: string;
  state: string;
  // Current period (most recent available)
  currentBldgs: number;
  currentUnits: number;
  currentPeriod: string;            // "YYYY-MM"
  // Prior year same period (for YoY comparison)
  priorBldgs: number;
  priorUnits: number;
  priorPeriod: string;              // "YYYY-MM"
  // YoY changes (used to populate BacklogInput in MPI engine)
  bldgsChangePercent: number;
  unitsChangePercent: number;
  // Convenience aliases consumed by scoreProjectBacklog()
  permitVolumeChangePercent: number;  // = bldgsChangePercent
  permitValueChangePercentYoY: number; // proxy = unitsChangePercent (unit count ≈ value proxy)
}

// ---- Bundle returned to callers ----
export interface CensusPermitBundle {
  msaPermits: Record<string, MSAPermitData>;  // keyed by msaId
  signals: SignalItem[];
  nationalBldgsChangePercent: number;
  nationalUnitsChangePercent: number;
  fetchedAt: string;
}

// ---- Cache helpers (Upstash Redis via env vars) ----
async function getFromCache(key: string): Promise<string | null> {
  const url = process.env.UPSTASH_REDIS_REST_URL;
  const token = process.env.UPSTASH_REDIS_REST_TOKEN;
  if (!url || !token) return null;
  try {
    const res = await fetch(`${url}/get/${key}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const json = await res.json();
    return json.result ?? null;
  } catch {
    return null;
  }
}

async function setCache(key: string, value: string, ttlSeconds: number): Promise<void> {
  const url = process.env.UPSTASH_REDIS_REST_URL;
  const token = process.env.UPSTASH_REDIS_REST_TOKEN;
  if (!url || !token) return;
  try {
    await fetch(`${url}/set/${key}/${encodeURIComponent(value)}/ex/${ttlSeconds}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
  } catch {
    // Cache failure is non-fatal
  }
}

// ---- Compute the most-recent available period ----
// Census BPS has ~2-month publication lag. We start at -2 months
// and fall back to -3 if the API returns no data for that period.
function getMostRecentAvailablePeriod(lagMonths: number = 2): { yearMonth: string; year: number; month: number } {
  const d = new Date();
  d.setMonth(d.getMonth() - lagMonths);
  return {
    yearMonth: `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`,
    year: d.getFullYear(),
    month: d.getMonth() + 1,
  };
}

function getPriorYearPeriod(current: { year: number; month: number }): string {
  return `${current.year - 1}-${String(current.month).padStart(2, '0')}`;
}

// ---- Fetch Census BPS data for all MSAs at a given time period ----
// Returns a map: cbsa → { bldgs, units }
async function fetchCensusAllMSAs(
  yearMonth: string
): Promise<Map<string, { bldgs: number; units: number }>> {
  const params = new URLSearchParams({
    get: 'BLDGS,UNITS',
    for: 'metropolitan statistical area:*',
    time: yearMonth,
  });

  const url = `https://api.census.gov/data/timeseries/bps/metro?${params}`;
  const response = await fetch(url, {
    headers: { Accept: 'application/json' },
  });

  if (!response.ok) {
    throw new Error(`Census BPS API error for ${yearMonth}: HTTP ${response.status}`);
  }

  // Census returns array-of-arrays: first row is the header
  const raw: string[][] = await response.json();
  if (!raw || raw.length < 2) {
    throw new Error(`Census BPS returned no data rows for ${yearMonth}`);
  }

  const [header, ...dataRows] = raw;
  const bldgsIdx = header.indexOf('BLDGS');
  const unitsIdx = header.indexOf('UNITS');
  const cbsaIdx  = header.indexOf('metropolitan statistical area');

  if (bldgsIdx < 0 || unitsIdx < 0 || cbsaIdx < 0) {
    throw new Error(`Census BPS response missing expected columns: ${header.join(', ')}`);
  }

  const result = new Map<string, { bldgs: number; units: number }>();
  for (const row of dataRows) {
    const cbsa  = row[cbsaIdx];
    const bldgs = parseInt(row[bldgsIdx] ?? '0', 10);
    const units = parseInt(row[unitsIdx] ?? '0', 10);
    if (cbsa && !isNaN(bldgs) && !isNaN(units)) {
      result.set(cbsa, { bldgs, units });
    }
  }

  return result;
}

// ---- Derive per-MSA permit metrics and signals ----
function buildPermitBundle(
  currentData: Map<string, { bldgs: number; units: number }>,
  priorData:   Map<string, { bldgs: number; units: number }>,
  currentPeriod: string,
  priorPeriod:   string
): CensusPermitBundle {
  const msaPermits: Record<string, MSAPermitData> = {};
  const signals: SignalItem[] = [];
  const now = new Date().toISOString();

  let nationalCurrentBldgs = 0;
  let nationalPriorBldgs   = 0;
  let nationalCurrentUnits = 0;
  let nationalPriorUnits   = 0;

  // Aggregate national totals from all rows in currentData
  for (const { bldgs, units } of currentData.values()) {
    nationalCurrentBldgs += bldgs;
    nationalCurrentUnits += units;
  }
  for (const { bldgs, units } of priorData.values()) {
    nationalPriorBldgs += bldgs;
    nationalPriorUnits += units;
  }

  const nationalBldgsChangePercent =
    nationalPriorBldgs > 0
      ? ((nationalCurrentBldgs - nationalPriorBldgs) / nationalPriorBldgs) * 100
      : 0;

  const nationalUnitsChangePercent =
    nationalPriorUnits > 0
      ? ((nationalCurrentUnits - nationalPriorUnits) / nationalPriorUnits) * 100
      : 0;

  // Per-MSA processing
  for (const [msaId, { cbsa, name, state }] of Object.entries(MSA_CBSA_MAP)) {
    const current = currentData.get(cbsa);
    const prior   = priorData.get(cbsa);

    // Skip if no data for this MSA in either period
    if (!current || !prior) continue;

    const bldgsChangePercent =
      prior.bldgs > 0
        ? ((current.bldgs - prior.bldgs) / prior.bldgs) * 100
        : 0;

    const unitsChangePercent =
      prior.units > 0
        ? ((current.units - prior.units) / prior.units) * 100
        : 0;

    msaPermits[msaId] = {
      msaId,
      msaName: name,
      state,
      currentBldgs: current.bldgs,
      currentUnits: current.units,
      currentPeriod,
      priorBldgs: prior.bldgs,
      priorUnits: prior.units,
      priorPeriod,
      bldgsChangePercent,
      unitsChangePercent,
      permitVolumeChangePercent: bldgsChangePercent,
      permitValueChangePercentYoY: unitsChangePercent,
    };

    // ---- Generate signals for meaningful permit changes ----
    const absBldgs = Math.abs(bldgsChangePercent);
    if (absBldgs >= 5) {
      const isIncrease = bldgsChangePercent > 0;
      const severity =
        absBldgs >= 30 ? 'critical' :
        absBldgs >= 20 ? 'high' :
        absBldgs >= 10 ? 'medium' : 'low';

      signals.push({
        id: `census-permits-${msaId}-${currentPeriod}`,
        type: isIncrease ? 'PERMIT_SURGE' : 'PERMIT_DECLINE',
        category: 'project_activity',
        severity,
        msaId,
        title: `${name}: Building permits ${isIncrease ? '▲' : '▼'} ${Math.abs(bldgsChangePercent).toFixed(1)}% YoY (${currentPeriod})`,
        description:
          `${name} issued ${current.bldgs.toLocaleString()} buildings (${current.units.toLocaleString()} units) in ${currentPeriod}, ` +
          `${isIncrease ? 'up' : 'down'} ${Math.abs(bldgsChangePercent).toFixed(1)}% from ${prior.bldgs.toLocaleString()} ` +
          `buildings (${prior.units.toLocaleString()} units) in ${priorPeriod}. ` +
          `${isIncrease ? 'Rising permit activity signals tightening sub backlog and labor demand.' : 'Declining activity may indicate softening demand or owner caution.'}`,
        source: 'U.S. Census Bureau — Building Permits Survey',
        sourceTier: 1,
        url: 'https://www.census.gov/construction/bps/',
        value: current.bldgs,
        unit: 'buildings',
        changeFromBaseline: bldgsChangePercent,
        timestamp: now,
        classifiedBy: 'api',
        confidence: 0.99,
      });
    }

    // Extra signal for very large unit swings (signals market heat more than small bldg changes)
    const absUnits = Math.abs(unitsChangePercent);
    if (absUnits >= 15 && absUnits > absBldgs + 5) {
      const isIncrease = unitsChangePercent > 0;
      const severity = absUnits >= 30 ? 'high' : 'medium';

      signals.push({
        id: `census-units-${msaId}-${currentPeriod}`,
        type: isIncrease ? 'PERMIT_SURGE' : 'PERMIT_DECLINE',
        category: 'project_activity',
        severity,
        msaId,
        title: `${name}: Unit permits ${isIncrease ? '▲' : '▼'} ${absUnits.toFixed(1)}% YoY — multifamily ${isIncrease ? 'surge' : 'pullback'}`,
        description:
          `Unit-level change (${absUnits.toFixed(1)}%) exceeds building count change (${absBldgs.toFixed(1)}%), ` +
          `indicating a ${isIncrease ? 'multifamily/apartment surge' : 'shift toward single-family or pullback in large projects'} in ${name}.`,
        source: 'U.S. Census Bureau — Building Permits Survey',
        sourceTier: 1,
        url: 'https://www.census.gov/construction/bps/',
        value: current.units,
        unit: 'units',
        changeFromBaseline: unitsChangePercent,
        timestamp: now,
        classifiedBy: 'api',
        confidence: 0.97,
      });
    }
  }

  // National-level permit signal
  if (Math.abs(nationalBldgsChangePercent) >= 5) {
    const isIncrease = nationalBldgsChangePercent > 0;
    const absPct = Math.abs(nationalBldgsChangePercent);
    const severity = absPct >= 20 ? 'high' : absPct >= 10 ? 'medium' : 'low';

    signals.push({
      id: `census-national-permits-${currentPeriod}`,
      type: isIncrease ? 'PERMIT_SURGE' : 'PERMIT_DECLINE',
      category: 'project_activity',
      severity,
      msaId: 'national',
      title: `National building permits ${isIncrease ? '▲' : '▼'} ${absPct.toFixed(1)}% YoY`,
      description:
        `National building permit activity ${isIncrease ? 'increased' : 'decreased'} ` +
        `${absPct.toFixed(1)}% YoY in ${currentPeriod}. ` +
        `${nationalCurrentBldgs.toLocaleString()} buildings vs ${nationalPriorBldgs.toLocaleString()} in prior year period.`,
      source: 'U.S. Census Bureau — Building Permits Survey',
      sourceTier: 1,
      url: 'https://www.census.gov/construction/bps/',
      value: nationalCurrentBldgs,
      unit: 'buildings',
      changeFromBaseline: nationalBldgsChangePercent,
      timestamp: now,
      classifiedBy: 'api',
      confidence: 0.99,
    });
  }

  return {
    msaPermits,
    signals,
    nationalBldgsChangePercent,
    nationalUnitsChangePercent,
    fetchedAt: now,
  };
}

// ---- Main Edge Function Handler ----
export default async function handler(req: Request): Promise<Response> {
  const url = new URL(req.url);
  const forceRefresh = url.searchParams.get('refresh') === 'true';
  const cacheKey = 'census-permits-v1';
  const cacheTTL = 3600 * 4; // 4 hours — permits data is monthly

  if (!forceRefresh) {
    const cached = await getFromCache(cacheKey);
    if (cached) {
      return new Response(cached, {
        headers: {
          'Content-Type': 'application/json',
          'X-Cache': 'HIT',
          'Cache-Control': 'public, max-age=3600',
        },
      });
    }
  }

  try {
    // Determine data periods (Census has ~2-month publication lag)
    const currentPeriodMeta = getMostRecentAvailablePeriod(2);
    const currentPeriod = currentPeriodMeta.yearMonth;
    const priorPeriod   = getPriorYearPeriod(currentPeriodMeta);

    // Attempt to fetch current period; fall back to -3 months if no data
    let currentData: Map<string, { bldgs: number; units: number }>;
    try {
      currentData = await fetchCensusAllMSAs(currentPeriod);
      if (currentData.size === 0) throw new Error('Empty response for current period');
    } catch {
      // Try one month earlier (some months publish late)
      const fallbackMeta = getMostRecentAvailablePeriod(3);
      currentData = await fetchCensusAllMSAs(fallbackMeta.yearMonth);
    }

    const priorData = await fetchCensusAllMSAs(priorPeriod);

    const bundle = buildPermitBundle(currentData, priorData, currentPeriod, priorPeriod);

    const response: EdgeResponse<CensusPermitBundle> = {
      data: bundle,
      error: null,
      cached: false,
      fetchedAt: new Date().toISOString(),
      source: 'U.S. Census Bureau — Building Permits Survey',
      stale: false,
    };

    const responseBody = JSON.stringify(response);
    await setCache(cacheKey, responseBody, cacheTTL);

    return new Response(responseBody, {
      headers: {
        'Content-Type': 'application/json',
        'X-Cache': 'MISS',
        'Cache-Control': 'public, max-age=3600',
      },
    });

  } catch (error) {
    const errorResponse: EdgeResponse<null> = {
      data: null,
      error: error instanceof Error ? error.message : 'Unknown Census fetch error',
      cached: false,
      fetchedAt: new Date().toISOString(),
      source: 'U.S. Census Bureau — Building Permits Survey',
      stale: false,
    };

    return new Response(JSON.stringify(errorResponse), {
      status: 503,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}
