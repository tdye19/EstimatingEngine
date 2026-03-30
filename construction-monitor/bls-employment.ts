// ============================================================
// api/labor/bls-employment.ts
// BLS Edge Function — Construction Trade Employment by Metro
//
// Data sourced from:
//   Bureau of Labor Statistics Public Data API v2
//   https://www.bls.gov/developers/api_faqs.htm
//   No API key required for up to 25 series/request
//
// Series IDs used:
//   LAUMT{FIPS}0000000000003  → Unemployment rate by MSA
//   CEU2000000001             → National construction employment (total)
//   For trade-level: ENU{FIPS}10521xxx → Quarterly census by county
// ============================================================

import type { EdgeResponse, BLSSeriesResult, SignalItem } from '../../src/types/index.ts';

// BLS Series IDs for construction trade unemployment by MSA
// Format: LAUMT + 6-digit FIPS + 0000000000003 (unemployment rate)
const MSA_SERIES_MAP: Record<string, { fips: string; name: string }> = {
  'detroit':      { fips: '198200', name: 'Detroit-Warren-Dearborn, MI' },
  'chicago':      { fips: '169800', name: 'Chicago-Naperville-Elgin, IL-IN-WI' },
  'houston':      { fips: '264200', name: 'Houston-The Woodlands-Sugar Land, TX' },
  'dallas':       { fips: '191000', name: 'Dallas-Fort Worth-Arlington, TX' },
  'phoenix':      { fips: '384200', name: 'Phoenix-Mesa-Chandler, AZ' },
  'atlanta':      { fips: '120600', name: 'Atlanta-Sandy Springs-Alpharetta, GA' },
  'denver':       { fips: '197400', name: 'Denver-Aurora-Lakewood, CO' },
  'seattle':      { fips: '426600', name: 'Seattle-Tacoma-Bellevue, WA' },
  'nashville':    { fips: '347000', name: 'Nashville-Davidson-Murfreesboro-Franklin, TN' },
  'columbus':     { fips: '184620', name: 'Columbus, OH' },
  'indianapolis': { fips: '267940', name: 'Indianapolis-Carmel-Anderson, IN' },
  'grand-rapids': { fips: '241620', name: 'Grand Rapids-Kentwood, MI' },
};

// National construction trade employment series
const NATIONAL_CONSTRUCTION_SERIES = [
  { id: 'CEU2000000001', label: 'Construction: Total Employment' },
  { id: 'CEU2023600001', label: 'Construction: Specialty Trade Contractors' },
  { id: 'CEU2022300001', label: 'Construction: Building, Highway, Heavy' },
  { id: 'CEU2023800001', label: 'Construction: Residential Specialty' },
  { id: 'CEU2023700001', label: 'Construction: Commercial Specialty' },
];

// PPI series for construction inputs (materials cost proxy)
const MATERIALS_PPI_SERIES = [
  { id: 'WPUID931',   label: 'PPI: Ready-Mix Concrete' },
  { id: 'WPU101',     label: 'PPI: Iron and Steel Products' },
  { id: 'WPU0811',    label: 'PPI: Softwood Lumber' },
  { id: 'WPU137',     label: 'PPI: Gypsum Products' },
  { id: 'WPU1321',    label: 'PPI: Flat Glass' },
  { id: 'WPUIP2311X1',label: 'PPI: Construction (inputs total)' },
];

interface BLSApiResponse {
  status: string;
  responseTime: number;
  message: string[];
  Results: {
    series: BLSSeriesResult[];
  };
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
    return json.result;
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

// ---- BLS API Fetcher ----
async function fetchBLSSeries(seriesIds: string[], startYear: string, endYear: string): Promise<BLSSeriesResult[]> {
  const response = await fetch('https://api.bls.gov/publicAPI/v2/timeseries/data/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      seriesid: seriesIds,
      startyear: startYear,
      endyear: endYear,
      // registrationkey: process.env.BLS_API_KEY  // optional, increases rate limit
    }),
  });

  if (!response.ok) {
    throw new Error(`BLS API error: ${response.status}`);
  }

  const data: BLSApiResponse = await response.json();

  if (data.status !== 'REQUEST_SUCCEEDED') {
    throw new Error(`BLS API failed: ${data.message.join(', ')}`);
  }

  return data.Results.series;
}

// ---- Signal Extraction from BLS Data ----
function extractConstructionSignals(series: BLSSeriesResult[]): SignalItem[] {
  const signals: SignalItem[] = [];
  const now = new Date().toISOString();
  const thisYear = new Date().getFullYear().toString();
  const lastYear = (new Date().getFullYear() - 1).toString();

  for (const s of series) {
    if (s.data.length < 2) continue;

    const latest = s.data[0];
    const prior = s.data[1];
    const latestVal = parseFloat(latest.value);
    const priorVal = parseFloat(prior.value);
    const changePercent = ((latestVal - priorVal) / priorVal) * 100;

    // Find series metadata
    const meta =
      NATIONAL_CONSTRUCTION_SERIES.find(x => x.id === s.seriesID) ||
      MATERIALS_PPI_SERIES.find(x => x.id === s.seriesID);
    if (!meta) continue;

    // Only generate signals for meaningful changes
    if (Math.abs(changePercent) < 0.5) continue;

    const isIncrease = changePercent > 0;
    const magnitude = Math.abs(changePercent);
    const severity =
      magnitude > 5 ? 'critical' :
      magnitude > 3 ? 'high' :
      magnitude > 1.5 ? 'medium' : 'low';

    // For PPI series
    if (s.seriesID.startsWith('WPU') || s.seriesID.startsWith('WPUIP')) {
      signals.push({
        id: `bls-ppi-${s.seriesID}-${latest.year}-${latest.period}`,
        type: s.seriesID.includes('101') ? 'STEEL_PRICE_CHANGE' :
              s.seriesID.includes('0811') ? 'LUMBER_PRICE_CHANGE' :
              s.seriesID.includes('931') ? 'CONCRETE_PRICE_CHANGE' :
              'MATERIAL_TARIFF_CHANGE',
        category: 'materials',
        severity,
        msaId: 'national',
        title: `${meta.label}: ${isIncrease ? '↑' : '↓'} ${magnitude.toFixed(1)}% MoM`,
        description: `${meta.label} changed ${changePercent.toFixed(2)}% from ${prior.periodName} ${prior.year} (${priorVal.toFixed(1)}) to ${latest.periodName} ${latest.year} (${latestVal.toFixed(1)}).`,
        source: 'Bureau of Labor Statistics — Producer Price Index',
        sourceTier: 1,
        url: `https://www.bls.gov/data/#prices`,
        value: latestVal,
        unit: 'index',
        changeFromBaseline: changePercent,
        timestamp: now,
        classifiedBy: 'api',
        confidence: 0.99,
      });
    }

    // For employment series
    if (s.seriesID.startsWith('CEU')) {
      const changeThousands = latestVal - priorVal;
      if (Math.abs(changeThousands) < 5) continue; // skip noise under 5k workers

      signals.push({
        id: `bls-emp-${s.seriesID}-${latest.year}-${latest.period}`,
        type: isIncrease ? 'LABOR_SURPLUS' : 'LABOR_SHORTAGE',
        category: 'labor',
        severity,
        msaId: 'national',
        title: `${meta.label}: ${isIncrease ? '+' : ''}${changeThousands.toFixed(0)}k workers MoM`,
        description: `${meta.label} ${isIncrease ? 'gained' : 'lost'} ${Math.abs(changeThousands).toFixed(0)}k workers from ${prior.periodName} ${prior.year} to ${latest.periodName} ${latest.year}. Current: ${(latestVal / 1000).toFixed(0)}k employed.`,
        source: 'Bureau of Labor Statistics — Current Employment Statistics',
        sourceTier: 1,
        url: `https://www.bls.gov/ces/`,
        value: latestVal,
        unit: 'thousands',
        changeFromBaseline: changePercent,
        timestamp: now,
        classifiedBy: 'api',
        confidence: 0.99,
      });
    }
  }

  return signals;
}

// ---- Main Edge Function Handler ----
export default async function handler(req: Request): Promise<Response> {
  const url = new URL(req.url);
  const type = url.searchParams.get('type') || 'employment'; // employment | ppi | both
  const forceRefresh = url.searchParams.get('refresh') === 'true';

  const cacheKey = `bls-${type}-v1`;
  const cacheTTL = 3600 * 4; // 4 hours (BLS updates monthly, cache generously)

  // Try cache first
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
    const currentYear = new Date().getFullYear().toString();
    const startYear = (new Date().getFullYear() - 2).toString();
    let allSeries: BLSSeriesResult[] = [];

    // BLS allows max 25 series per request without key, 50 with key
    if (type === 'employment' || type === 'both') {
      const empSeries = await fetchBLSSeries(
        NATIONAL_CONSTRUCTION_SERIES.map(s => s.id),
        startYear,
        currentYear
      );
      allSeries = [...allSeries, ...empSeries];
    }

    if (type === 'ppi' || type === 'both') {
      const ppiSeries = await fetchBLSSeries(
        MATERIALS_PPI_SERIES.map(s => s.id),
        startYear,
        currentYear
      );
      allSeries = [...allSeries, ...ppiSeries];
    }

    const signals = extractConstructionSignals(allSeries);

    const response: EdgeResponse<{
      series: BLSSeriesResult[];
      signals: SignalItem[];
      seriesCount: number;
    }> = {
      data: {
        series: allSeries,
        signals,
        seriesCount: allSeries.length,
      },
      error: null,
      cached: false,
      fetchedAt: new Date().toISOString(),
      source: 'Bureau of Labor Statistics Public Data API v2',
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
      error: error instanceof Error ? error.message : 'Unknown BLS fetch error',
      cached: false,
      fetchedAt: new Date().toISOString(),
      source: 'Bureau of Labor Statistics Public Data API v2',
      stale: false,
    };

    return new Response(JSON.stringify(errorResponse), {
      status: 503,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}
