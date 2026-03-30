// ============================================================
// api/macro/fred-rates.ts
// FRED Edge Function — Federal Reserve Economic Data
//
// Data sourced from:
//   Federal Reserve Bank of St. Louis FRED API
//   https://fred.stlouisfed.org/docs/api/fred/
//   Free key required: https://fred.stlouisfed.org/docs/api/api_key.html
//
// Series used:
//   FEDFUNDS     → Federal Funds Rate (proxy for construction loan rates)
//   MORTGAGE30US → 30-Year Mortgage Rate (residential construction demand)
//   CUUR0000SAH3 → CPI: Shelter (owner equivalent rent)
//   PCUEZPEZP    → PPI: New Construction
//   MEHOINUSA672N→ Median Household Income (construction demand signal)
// ============================================================

import type { EdgeResponse, SignalItem } from '../../src/types/index.ts';

interface FREDObservation {
  realtime_start: string;
  realtime_end: string;
  date: string;
  value: string;
}

interface FREDSeriesResponse {
  realtime_start: string;
  realtime_end: string;
  observation_start: string;
  observation_end: string;
  units: string;
  output_type: number;
  file_type: string;
  order_by: string;
  sort_order: string;
  count: number;
  offset: number;
  limit: number;
  observations: FREDObservation[];
}

// Curated FRED series for construction estimating context
export const FRED_SERIES = {
  // Rate environment (affects owner financing, construction loans)
  FEDFUNDS: {
    label: 'Federal Funds Rate',
    units: '%',
    category: 'macro' as const,
    impactContext: 'Directly affects construction loan rates. Every 1% increase adds ~$1.5-2.5/SF to financing cost on typical commercial project.',
  },
  MORTGAGE30US: {
    label: '30-Year Mortgage Rate',
    units: '%',
    category: 'macro' as const,
    impactContext: 'Primary driver of residential construction demand. >7% historically suppresses residential starts 15-25%.',
  },

  // Construction cost indices
  WPUIP2311X1: {
    label: 'PPI: Inputs to Construction Industries',
    units: 'Index 1982=100',
    category: 'materials' as const,
    impactContext: 'Composite materials cost index. Best single proxy for overall construction cost escalation.',
  },
  PCU2361002361: {
    label: 'PPI: New Industrial Building Construction',
    units: 'Index 2005=100',
    category: 'materials' as const,
    impactContext: 'Measures actual contractor bid prices for industrial construction.',
  },
  PCU2362002362: {
    label: 'PPI: New Office Building Construction',
    units: 'Index 2005=100',
    category: 'materials' as const,
    impactContext: 'Measures actual contractor bid prices for commercial/office construction.',
  },

  // Commodity spot prices
  WPU101: {
    label: 'PPI: Iron and Steel Mill Products',
    units: 'Index 1982=100',
    category: 'materials' as const,
    impactContext: 'Steel commodity pricing. Structural steel and rebar costs track this within 2-3 months.',
  },
  WPU0811: {
    label: 'PPI: Softwood Lumber',
    units: 'Index 1982=100',
    category: 'materials' as const,
    impactContext: 'Lumber pricing — affects wood framing, formwork, temporary works costs.',
  },
  WPUID931: {
    label: 'PPI: Ready-Mix Concrete',
    units: 'Index 1982=100',
    category: 'materials' as const,
    impactContext: 'Ready-mix pricing direct from producers. Lags cement/aggregate inputs by 1-2 months.',
  },

  // Construction activity
  HOUST: {
    label: 'Housing Starts (National)',
    units: 'Thousands of Units',
    category: 'project_activity' as const,
    impactContext: 'Leading indicator for residential construction demand. Affects framing/MEP sub availability.',
  },
  PERMIT: {
    label: 'Building Permits (National)',
    units: 'Thousands of Units',
    category: 'project_activity' as const,
    impactContext: '2-6 month lead time indicator for construction activity. Drives sub backlog and labor demand.',
  },
  TLRESCONS: {
    label: 'Construction Spending (Total)',
    units: 'Millions of Dollars',
    category: 'project_activity' as const,
    impactContext: 'Monthly construction spending. Market-level indicator of contractor backlog saturation.',
  },
};

type FREDSeriesId = keyof typeof FRED_SERIES;

// Cache helpers
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
  } catch { return null; }
}

async function setCache(key: string, value: string, ttlSeconds: number): Promise<void> {
  const url = process.env.UPSTASH_REDIS_REST_URL;
  const token = process.env.UPSTASH_REDIS_REST_TOKEN;
  if (!url || !token) return;
  try {
    await fetch(`${url}/set/${key}/${encodeURIComponent(value)}/ex/${ttlSeconds}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
  } catch { /* non-fatal */ }
}

// Fetch single FRED series
async function fetchFREDSeries(seriesId: string, limit: number = 13): Promise<FREDObservation[]> {
  const apiKey = process.env.FRED_API_KEY;
  if (!apiKey) throw new Error('FRED_API_KEY not configured');

  const params = new URLSearchParams({
    series_id: seriesId,
    api_key: apiKey,
    file_type: 'json',
    sort_order: 'desc',
    limit: limit.toString(),
    observation_start: '2020-01-01',
  });

  const response = await fetch(`https://api.stlouisfed.org/fred/series/observations?${params}`);
  if (!response.ok) throw new Error(`FRED API error for ${seriesId}: ${response.status}`);

  const data: FREDSeriesResponse = await response.json();
  return data.observations.filter(o => o.value !== '.');
}

// Convert FRED observations to construction signals
function buildSignals(
  seriesId: FREDSeriesId,
  observations: FREDObservation[]
): SignalItem[] {
  const signals: SignalItem[] = [];
  const meta = FRED_SERIES[seriesId];
  if (observations.length < 2) return signals;

  const latest = observations[0];
  const prior = observations[1];
  const latestVal = parseFloat(latest.value);
  const priorVal = parseFloat(prior.value);
  if (isNaN(latestVal) || isNaN(priorVal)) return signals;

  const change = latestVal - priorVal;
  const changePercent = (change / priorVal) * 100;
  const isIncrease = change > 0;

  // Thresholds vary by series type
  const thresholds: Record<string, number> = {
    FEDFUNDS: 0.1,       // 10 basis points
    MORTGAGE30US: 0.1,
    HOUST: 2,            // 2% change in starts
    PERMIT: 2,
    TLRESCONS: 1,
    default: 1,          // 1% for index series
  };

  const threshold = thresholds[seriesId] || thresholds.default;
  if (Math.abs(changePercent) < threshold) return signals;

  const absChange = Math.abs(changePercent);
  const severity =
    absChange > 8 ? 'critical' :
    absChange > 4 ? 'high' :
    absChange > 2 ? 'medium' : 'low';

  signals.push({
    id: `fred-${seriesId}-${latest.date}`,
    type: seriesId === 'FEDFUNDS' || seriesId === 'MORTGAGE30US' ? 'RATE_CHANGE' :
          meta.category === 'materials' ? 'MATERIAL_TARIFF_CHANGE' :
          meta.category === 'project_activity' ? 'PERMIT_SURGE' : 'REGULATORY_CHANGE',
    category: meta.category,
    severity,
    msaId: 'national',
    title: `${meta.label}: ${isIncrease ? '↑' : '↓'} ${changePercent.toFixed(2)}% (${latest.date})`,
    description: `${meta.label} moved from ${priorVal.toFixed(2)} ${meta.units} (${prior.date}) to ${latestVal.toFixed(2)} ${meta.units} (${latest.date}). ${meta.impactContext}`,
    source: 'Federal Reserve Bank of St. Louis — FRED',
    sourceTier: 1,
    url: `https://fred.stlouisfed.org/series/${seriesId}`,
    value: latestVal,
    unit: meta.units,
    changeFromBaseline: changePercent,
    timestamp: new Date().toISOString(),
    classifiedBy: 'api',
    confidence: 1.0,
  });

  return signals;
}

export interface FREDDataBundle {
  series: Record<string, FREDObservation[]>;
  signals: SignalItem[];
  rateEnvironment: {
    fedFunds: number;
    mortgage30: number;
    constructionLoanProxyRate: number; // fed funds + typical spread
    rateCategory: 'low' | 'moderate' | 'high' | 'very_high';
  };
}

// Compute rate environment category for MPI
function categorizeRateEnvironment(fedFunds: number, mortgage30: number): FREDDataBundle['rateEnvironment'] {
  const constructionLoanProxyRate = fedFunds + 2.25; // typical spread

  const rateCategory =
    fedFunds < 2.0 ? 'low' :
    fedFunds < 4.0 ? 'moderate' :
    fedFunds < 5.5 ? 'high' : 'very_high';

  return {
    fedFunds,
    mortgage30,
    constructionLoanProxyRate,
    rateCategory,
  };
}

export default async function handler(req: Request): Promise<Response> {
  const cacheKey = 'fred-construction-v1';
  const cacheTTL = 3600 * 6; // 6 hours (FRED updates daily at most)

  const cached = await getFromCache(cacheKey);
  if (cached) {
    return new Response(cached, {
      headers: { 'Content-Type': 'application/json', 'X-Cache': 'HIT' },
    });
  }

  try {
    const seriesIds = Object.keys(FRED_SERIES) as FREDSeriesId[];
    const seriesData: Record<string, FREDObservation[]> = {};
    const allSignals: SignalItem[] = [];

    // Fetch all series (FRED has no bulk endpoint, must loop)
    // Use Promise.all with rate limiting courtesy
    const BATCH_SIZE = 4;
    for (let i = 0; i < seriesIds.length; i += BATCH_SIZE) {
      const batch = seriesIds.slice(i, i + BATCH_SIZE);
      const results = await Promise.allSettled(
        batch.map(id => fetchFREDSeries(id))
      );

      results.forEach((result, idx) => {
        const id = batch[idx];
        if (result.status === 'fulfilled') {
          seriesData[id] = result.value;
          allSignals.push(...buildSignals(id, result.value));
        } else {
          console.error(`FRED fetch failed for ${id}:`, result.reason);
          seriesData[id] = [];
        }
      });

      // Polite delay between batches
      if (i + BATCH_SIZE < seriesIds.length) {
        await new Promise(resolve => setTimeout(resolve, 200));
      }
    }

    // Build rate environment summary
    const fedFundsObs = seriesData['FEDFUNDS'];
    const mortgage30Obs = seriesData['MORTGAGE30US'];
    const fedFunds = fedFundsObs?.length ? parseFloat(fedFundsObs[0].value) : 0;
    const mortgage30 = mortgage30Obs?.length ? parseFloat(mortgage30Obs[0].value) : 0;
    const rateEnvironment = categorizeRateEnvironment(fedFunds, mortgage30);

    const bundle: FREDDataBundle = {
      series: seriesData,
      signals: allSignals,
      rateEnvironment,
    };

    const response: EdgeResponse<FREDDataBundle> = {
      data: bundle,
      error: null,
      cached: false,
      fetchedAt: new Date().toISOString(),
      source: 'Federal Reserve Bank of St. Louis — FRED API',
      stale: false,
    };

    const responseBody = JSON.stringify(response);
    await setCache(cacheKey, responseBody, cacheTTL);

    return new Response(responseBody, {
      headers: { 'Content-Type': 'application/json', 'X-Cache': 'MISS' },
    });

  } catch (error) {
    return new Response(JSON.stringify({
      data: null,
      error: error instanceof Error ? error.message : 'FRED fetch error',
      cached: false,
      fetchedAt: new Date().toISOString(),
      source: 'FRED',
      stale: false,
    }), {
      status: 503,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}
