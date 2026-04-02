// ============================================================
// api/mpi-scores.ts
// MPI Scores Orchestrator — Edge Function
//
// Aggregates data from three sources:
//   1. BLS Public API v2   → Labor availability + materials PPI
//   2. FRED API            → Rate environment + national PPI + activity
//   3. Census BPS API      → Building permits by MSA (no key needed)
//
// Runs calculateMPI() for each monitored MSA, then returns a
// dashboard-ready JSON array. The HTML dashboard calls this
// single endpoint instead of fetching the three sources separately.
//
// Cache: Upstash Redis, 1-hour TTL (BLS monthly, FRED daily,
//        Census monthly — 1hr keeps the UI live within API limits)
// ============================================================

import type { EdgeResponse, SignalItem } from '../index.ts';
import {
  calculateMPI,
  interpretMPI,
  MPI_WEIGHTS,
  MSA_BASELINE_RISK,
} from '../mpi-engine.ts';
import type {
  MPIInputBundle,
  MaterialsInput,
  LaborInput,
  BacklogInput,
  SupplyChainInput,
  FinancialDistressInput,
} from '../mpi-engine.ts';

// ---- MSA Master Catalog ----
// Defines every MSA we score: geographic display info + API identifiers
interface MSACatalogEntry {
  id: string;
  shortName: string;
  fullName: string;
  state: string;
  lat: number;    // Latitude for Leaflet map
  lng: number;    // Longitude for Leaflet map
  blsFips: string;  // 6-digit BLS LAUS FIPS code
  censusCbsa: string; // 5-digit Census CBSA code
}

const MSA_CATALOG: MSACatalogEntry[] = [
  { id: 'phoenix',        shortName: 'Phoenix',        fullName: 'Phoenix-Mesa-Chandler, AZ',                    state: 'AZ', lat: 33.4484, lng: -112.0740, blsFips: '384200', censusCbsa: '38060' },
  { id: 'nashville',      shortName: 'Nashville',      fullName: 'Nashville-Davidson--Murfreesboro--Franklin, TN',state: 'TN', lat: 36.1627, lng:  -86.7816, blsFips: '347000', censusCbsa: '34980' },
  { id: 'seattle',        shortName: 'Seattle',        fullName: 'Seattle-Tacoma-Bellevue, WA',                  state: 'WA', lat: 47.6062, lng: -122.3321, blsFips: '426600', censusCbsa: '42660' },
  { id: 'dallas',         shortName: 'Dallas',         fullName: 'Dallas-Fort Worth-Arlington, TX',              state: 'TX', lat: 32.7767, lng:  -96.7970, blsFips: '191000', censusCbsa: '19100' },
  { id: 'detroit',        shortName: 'Detroit',        fullName: 'Detroit-Warren-Dearborn, MI',                  state: 'MI', lat: 42.3314, lng:  -83.0458, blsFips: '198200', censusCbsa: '19820' },
  { id: 'chicago',        shortName: 'Chicago',        fullName: 'Chicago-Naperville-Elgin, IL-IN-WI',           state: 'IL', lat: 41.8781, lng:  -87.6298, blsFips: '169800', censusCbsa: '16980' },
  { id: 'columbus',       shortName: 'Columbus',       fullName: 'Columbus, OH',                                 state: 'OH', lat: 39.9612, lng:  -82.9988, blsFips: '184620', censusCbsa: '18140' },
  { id: 'indianapolis',   shortName: 'Indianapolis',   fullName: 'Indianapolis-Carmel-Anderson, IN',             state: 'IN', lat: 39.7684, lng:  -86.1581, blsFips: '267940', censusCbsa: '26900' },
  { id: 'grand-rapids',   shortName: 'Grand Rapids',   fullName: 'Grand Rapids-Kentwood, MI',                   state: 'MI', lat: 42.9634, lng:  -85.6681, blsFips: '241620', censusCbsa: '24340' },
  { id: 'houston',        shortName: 'Houston',        fullName: 'Houston-The Woodlands-Sugar Land, TX',         state: 'TX', lat: 29.7604, lng:  -95.3698, blsFips: '264200', censusCbsa: '26420' },
  { id: 'denver',         shortName: 'Denver',         fullName: 'Denver-Aurora-Lakewood, CO',                   state: 'CO', lat: 39.7392, lng: -104.9903, blsFips: '197400', censusCbsa: '19740' },
  { id: 'atlanta',        shortName: 'Atlanta',        fullName: 'Atlanta-Sandy Springs-Alpharetta, GA',         state: 'GA', lat: 33.7490, lng:  -84.3880, blsFips: '120600', censusCbsa: '12060' },
  // ---- 8 new MSAs (Sprint 14) ----
  { id: 'lansing',        shortName: 'Lansing',        fullName: 'Lansing-East Lansing, MI',                     state: 'MI', lat: 42.7325, lng:  -84.5555, blsFips: '290600', censusCbsa: '29620' },
  { id: 'virginia-beach', shortName: 'Virginia Beach', fullName: 'Virginia Beach-Norfolk-Newport News, VA-NC',   state: 'VA', lat: 36.8529, lng:  -75.9780, blsFips: '471600', censusCbsa: '47260' },
  { id: 'richmond',       shortName: 'Richmond',       fullName: 'Richmond, VA',                                 state: 'VA', lat: 37.5407, lng:  -77.4360, blsFips: '400600', censusCbsa: '40060' },
  { id: 'knoxville',      shortName: 'Knoxville',      fullName: 'Knoxville, TN',                                state: 'TN', lat: 35.9606, lng:  -83.9207, blsFips: '280600', censusCbsa: '28940' },
  { id: 'raleigh',        shortName: 'Raleigh',        fullName: 'Raleigh-Cary, NC',                             state: 'NC', lat: 35.7796, lng:  -78.6382, blsFips: '390400', censusCbsa: '39580' },
  { id: 'san-antonio',    shortName: 'San Antonio',    fullName: 'San Antonio-New Braunfels, TX',                state: 'TX', lat: 29.4241, lng:  -98.4936, blsFips: '416600', censusCbsa: '41700' },
];

// ---- Dashboard-facing data shape ----
// Extends MPIScore with display properties the HTML prototype needs
export interface DashboardMSAData {
  id: string;
  name: string;         // shortName for display
  state: string;
  score: number;
  tier: string;
  trend: string;
  delta: number;        // trendDelta rounded
  lat: number;
  lng: number;
  alerts: number;       // alert count
  components: {
    materials: number;  // rawScore 0-100
    labor: number;
    backlog: number;
    supply: number;
    distress: number;
  };
  topAlert: {
    title: string;
    body: string;
    severity: string;
    tags: string[];
    impact: string;
  } | null;
  rec: string;
  lastUpdated: string;
}

// ---- Cache helpers ----
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

// ============================================================
// BLS DATA FETCHING
// ============================================================

interface BLSApiResponse {
  status: string;
  message: string[];
  Results: { series: Array<{ seriesID: string; data: Array<{ year: string; period: string; periodName: string; value: string; footnotes: object[] }> }> };
}

// National construction employment + PPI series to fetch
const BLS_NATIONAL_SERIES = [
  'CEU2000000001',  // Construction: Total Employment
  'CEU2023600001',  // Construction: Specialty Trade Contractors
  'WPUID931',       // PPI: Ready-Mix Concrete
  'WPU101',         // PPI: Iron and Steel Products
  'WPU0811',        // PPI: Softwood Lumber
  'WPUIP2311X1',    // PPI: Construction Inputs (composite)
];

async function fetchBLSSeries(
  seriesIds: string[],
  startYear: string,
  endYear: string
): Promise<BLSApiResponse['Results']['series']> {
  const response = await fetch('https://api.bls.gov/publicAPI/v2/timeseries/data/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ seriesid: seriesIds, startyear: startYear, endyear: endYear }),
  });

  if (!response.ok) throw new Error(`BLS API error: HTTP ${response.status}`);
  const data: BLSApiResponse = await response.json();
  if (data.status !== 'REQUEST_SUCCEEDED') {
    throw new Error(`BLS API failed: ${data.message?.join(', ')}`);
  }
  return data.Results.series;
}

// Fetch MSA-level construction unemployment rates via BLS LAUS
// Series format: LAUMT + 6-digit FIPS + 0000000000003
async function fetchBLSMSAUnemployment(
  msas: MSACatalogEntry[],
  startYear: string,
  endYear: string
): Promise<Map<string, number>> {  // msaId → latest unemployment rate %
  const seriesIds = msas.map(m => `LAUMT${m.blsFips}0000000000003`);
  const series = await fetchBLSSeries(seriesIds, startYear, endYear);

  const result = new Map<string, number>();
  for (const s of series) {
    // Extract the FIPS from the series ID: strip LAUMT prefix and suffix
    const fips = s.seriesID.replace('LAUMT', '').replace('0000000000003', '');
    const msa = msas.find(m => m.blsFips === fips);
    if (!msa) continue;

    const latestRow = s.data[0];
    if (latestRow) {
      const rate = parseFloat(latestRow.value);
      if (!isNaN(rate)) result.set(msa.id, rate);
    }
  }
  return result;
}

// Parse PPI YoY change from BLS series data
function parsePPIYoYChange(
  seriesData: BLSApiResponse['Results']['series'][number]
): number {
  // BLS returns data in desc order; data[0] = latest, data[12] ≈ year ago
  if (seriesData.data.length < 13) return 0;
  const latest = parseFloat(seriesData.data[0].value);
  const yearAgo = parseFloat(seriesData.data[12].value);
  if (isNaN(latest) || isNaN(yearAgo) || yearAgo === 0) return 0;
  return ((latest - yearAgo) / yearAgo) * 100;
}

// ============================================================
// FRED DATA FETCHING
// ============================================================

interface FREDObservation { date: string; value: string; }
interface FREDResponse {
  observations: FREDObservation[];
}

async function fetchFREDSeries(
  seriesId: string,
  limit: number = 14
): Promise<FREDObservation[]> {
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

  const res = await fetch(`https://api.stlouisfed.org/fred/series/observations?${params}`);
  if (!res.ok) throw new Error(`FRED API error for ${seriesId}: HTTP ${res.status}`);

  const data: FREDResponse = await res.json();
  return data.observations.filter(o => o.value !== '.');
}

// Compute YoY % change from FRED observations (desc order, [0]=latest, [12]=year ago)
function fredYoYChange(obs: FREDObservation[]): number {
  if (obs.length < 13) return 0;
  const latest = parseFloat(obs[0].value);
  const yearAgo = parseFloat(obs[12].value);
  if (isNaN(latest) || isNaN(yearAgo) || yearAgo === 0) return 0;
  return ((latest - yearAgo) / yearAgo) * 100;
}

function fredLatestValue(obs: FREDObservation[]): number {
  if (!obs.length) return 0;
  return parseFloat(obs[0].value) || 0;
}

// ============================================================
// CENSUS BPS DATA FETCHING
// ============================================================

async function fetchCensusPermits(
  yearMonth: string
): Promise<Map<string, { bldgs: number; units: number }>> {
  const params = new URLSearchParams({
    get: 'BLDGS,UNITS',
    for: 'metropolitan statistical area:*',
    time: yearMonth,
  });

  const res = await fetch(
    `https://api.census.gov/data/timeseries/bps/metro?${params}`,
    { headers: { Accept: 'application/json' } }
  );
  if (!res.ok) throw new Error(`Census BPS error for ${yearMonth}: HTTP ${res.status}`);

  const raw: string[][] = await res.json();
  if (!raw || raw.length < 2) return new Map();

  const [header, ...rows] = raw;
  const bldgsIdx = header.indexOf('BLDGS');
  const unitsIdx = header.indexOf('UNITS');
  const cbsaIdx  = header.indexOf('metropolitan statistical area');
  if (bldgsIdx < 0 || unitsIdx < 0 || cbsaIdx < 0) return new Map();

  const result = new Map<string, { bldgs: number; units: number }>();
  for (const row of rows) {
    const cbsa  = row[cbsaIdx];
    const bldgs = parseInt(row[bldgsIdx] ?? '0', 10);
    const units = parseInt(row[unitsIdx] ?? '0', 10);
    if (cbsa && !isNaN(bldgs)) result.set(cbsa, { bldgs, units: isNaN(units) ? 0 : units });
  }
  return result;
}

function getCensusPeriods(): { current: string; prior: string } {
  const d = new Date();
  d.setMonth(d.getMonth() - 2); // ~2-month publication lag
  const currentMonth = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
  const priorMonth   = `${d.getFullYear() - 1}-${String(d.getMonth() + 1).padStart(2, '0')}`;
  return { current: currentMonth, prior: priorMonth };
}

// ============================================================
// MPI INPUT ASSEMBLY
// ============================================================

interface FetchedData {
  // PPI YoY changes (from BLS or FRED)
  steelPPIYoY: number;
  concretePPIYoY: number;
  lumberPPIYoY: number;
  constructionInputsPPIYoY: number;
  // National labor (from BLS employment series)
  nationalConstructionEmployment: number;  // thousands
  nationalEmploymentChangePct: number;     // MoM %
  nationalTradeUnemploymentRate: number;   // % (derived or fallback)
  // Rate environment (from FRED)
  fedFundsRate: number;
  constructionSpendingChangePct: number;   // FRED TLRESCONS YoY %
  // Per-MSA unemployment (from BLS LAUS)
  msaUnemploymentRates: Map<string, number>;
  // Per-MSA permit data (from Census)
  censusCurrentData: Map<string, { bldgs: number; units: number }>;
  censusPriorData:   Map<string, { bldgs: number; units: number }>;
  // All signals collected
  allSignals: SignalItem[];
}

function assembleMaterialsInput(data: FetchedData): MaterialsInput {
  return {
    steelPPIChangePercent:             data.steelPPIYoY,
    concretePPIChangePercent:          data.concretePPIYoY,
    lumberPPIChangePercent:            data.lumberPPIYoY,
    constructionInputsPPIChange:       data.constructionInputsPPIYoY,
    activeTariffSignals:
      data.allSignals.filter(s => s.type === 'MATERIAL_TARIFF_CHANGE' || s.type === 'TARIFF_IMPOSED').length,
    supplyDisruptionSignals:
      data.allSignals.filter(s => s.type === 'CEMENT_SUPPLY_DISRUPTION' || s.type === 'PLANT_CLOSURE').length,
  };
}

function assembleLaborInput(
  msaId: string,
  data: FetchedData,
  msaSignals: SignalItem[]
): LaborInput {
  const localRate = data.msaUnemploymentRates.get(msaId);
  // Fall back to national proxy (construction trades typically run ~1pt above total)
  const tradeUnemploymentRate = localRate ?? data.nationalTradeUnemploymentRate + 1.0;

  return {
    tradeUnemploymentRate,
    nationalAvgTradeUnemployment: data.nationalTradeUnemploymentRate,
    activeStrikeCount: 0,   // No free real-time strike API; signals from news feed in future
    cbaDaysToExpiry:   999, // No free CBA calendar in MVP
    laborNewsSignalCount: msaSignals.filter(s => s.category === 'labor').length,
    prevailingWageChangePercent: undefined,
    apprenticeshipRatio: undefined,
  };
}

function assembleBacklogInput(
  msa: MSACatalogEntry,
  data: FetchedData,
  msaSignals: SignalItem[]
): BacklogInput {
  const current = data.censusCurrentData.get(msa.censusCbsa);
  const prior   = data.censusPriorData.get(msa.censusCbsa);

  let permitVolumeChangePct = 0;
  let permitValueChangePct  = 0;

  if (current && prior && prior.bldgs > 0) {
    permitVolumeChangePct = ((current.bldgs - prior.bldgs) / prior.bldgs) * 100;
  }
  if (current && prior && prior.units > 0) {
    permitValueChangePct = ((current.units - prior.units) / prior.units) * 100;
  }

  const megaCount = msaSignals.filter(s => s.type === 'MEGA_PROJECT_ANNOUNCED').length;
  const federalCount = msaSignals.filter(s => s.type === 'FEDERAL_AWARD_LARGE').length;

  return {
    permitVolumeChangePercent:   permitVolumeChangePct,
    permitValueChangePercentYoY: permitValueChangePct,
    constructionSpendingChangePercent: data.constructionSpendingChangePct,
    megaProjectAnnouncementCount: megaCount,
    federalAwardCount:            federalCount,
    historicalBacklogMonths:      3, // MVP default; Dodge Data integration planned
  };
}

function assembleSupplyChainInput(data: FetchedData, msaSignals: SignalItem[]): SupplyChainInput {
  const leadTimeSignals = msaSignals.filter(s => s.type === 'LEAD_TIME_SPIKE').length;
  const supplierSignals = msaSignals.filter(s => s.type === 'SUPPLIER_DISTRESS').length;
  const tariffMaterials = data.allSignals.filter(s =>
    s.type === 'MATERIAL_TARIFF_CHANGE' || s.type === 'TARIFF_IMPOSED'
  ).length;

  return {
    portCongestionLevel:    'none',  // Port data integration planned (MARAD)
    plantClosureCount:       0,      // Plant closure signals from news feed in future
    leadTimeSpikeSignals:    leadTimeSignals,
    supplierDistressSignals: supplierSignals,
    weatherDisruptionActive: false,  // NOAA integration planned
    tariffImpactedMaterials: Math.min(4, tariffMaterials),
  };
}

function assembleFinancialDistressInput(_data: FetchedData, _msaSignals: SignalItem[]): FinancialDistressInput {
  // Financial distress APIs (lien filings, bankruptcy) require paid data (D&B, court records)
  // Use 'normal' velocity as MVP default — will upgrade with court API integration
  return {
    lienFilingVelocity:     'normal',
    bankruptcyFilingsCount:  0,
    suretyClaimsCount:       0,
    paymentDefaultNewsCount: 0,
    creditDowngradeSignals:  0,
  };
}

// ============================================================
// DASHBOARD SHAPE BUILDER
// ============================================================

function buildDashboardEntry(
  msa: MSACatalogEntry,
  bundle: MPIInputBundle,
  data: FetchedData
): DashboardMSAData {
  const mpiScore = calculateMPI(bundle);
  const interp   = interpretMPI(mpiScore);

  const topConvergence = mpiScore.alerts[0] ?? null;

  let topAlert: DashboardMSAData['topAlert'] = null;
  if (topConvergence) {
    const impact = topConvergence.estimatedCostImpact;
    const impactText = impact
      ? `+${(impact.estimatedRangeLow * 100).toFixed(0)}–${(impact.estimatedRangeHigh * 100).toFixed(0)}% on ${impact.tradeAffected}`
      : 'Cost impact: under assessment';

    topAlert = {
      title:    topConvergence.title,
      body:     topConvergence.body,
      severity: topConvergence.severity,
      tags:     topConvergence.categories,
      impact:   impactText,
    };
  }

  return {
    id:    msa.id,
    name:  msa.shortName,
    state: msa.state,
    score: mpiScore.score,
    tier:  mpiScore.tier,
    trend: mpiScore.trend,
    delta: mpiScore.trendDelta,
    lat:   msa.lat,
    lng:   msa.lng,
    alerts: mpiScore.alerts.length,
    components: {
      materials: Math.round(mpiScore.components.materialsCostTrend.rawScore),
      labor:     Math.round(mpiScore.components.laborAvailability.rawScore),
      backlog:   Math.round(mpiScore.components.projectBacklog.rawScore),
      supply:    Math.round(mpiScore.components.supplyChainStress.rawScore),
      distress:  Math.round(mpiScore.components.financialDistress.rawScore),
    },
    topAlert,
    rec: interp.recommendation,
    lastUpdated: mpiScore.lastUpdated,
  };
}

// ============================================================
// DATA STRIP — national indicators for the dashboard header bar
// ============================================================

export interface DataStripValues {
  ppiConstructionInputs:   { value: number; changeYoY: number };
  ppiSteelMill:            { value: number; changeYoY: number };
  ppiReadyMixConcrete:     { value: number; changeYoY: number };
  constructionEmployment:  { valueThousands: number; changeMoM: number };
  buildingPermits:         { valueThousands: number; changeMoM: number };
  fedFundsRate:            { value: number; unchanged: boolean };
}

// ============================================================
// MAIN HANDLER
// ============================================================

export default async function handler(req: Request): Promise<Response> {
  const url = new URL(req.url);
  const forceRefresh = url.searchParams.get('refresh') === 'true';
  const cacheKey = 'mpi-scores-v2';
  const cacheTTL = 3600; // 1 hour

  if (!forceRefresh) {
    const cached = await getFromCache(cacheKey);
    if (cached) {
      return new Response(cached, {
        headers: {
          'Content-Type': 'application/json',
          'X-Cache': 'HIT',
          'Cache-Control': 'public, max-age=600',
        },
      });
    }
  }

  try {
    const currentYear = new Date().getFullYear().toString();
    const startYear   = (new Date().getFullYear() - 2).toString();

    // ---- Fetch all data sources concurrently ----
    const [
      blsNationalResult,
      blsMSAResult,
      fredFEDFUNDS,
      fredWPUIP2311X1,
      fredWPU101,
      fredWPU0811,
      fredWPUID931,
      fredTLRESCONS,
      fredPERMIT,
      censusCurrentResult,
      censusPriorResult,
    ] = await Promise.allSettled([
      // BLS national series (employment + PPI)
      fetchBLSSeries(BLS_NATIONAL_SERIES, startYear, currentYear),
      // BLS MSA unemployment rates
      fetchBLSMSAUnemployment(MSA_CATALOG, startYear, currentYear),
      // FRED macro series
      fetchFREDSeries('FEDFUNDS', 14),
      fetchFREDSeries('WPUIP2311X1', 14),
      fetchFREDSeries('WPU101', 14),
      fetchFREDSeries('WPU0811', 14),
      fetchFREDSeries('WPUID931', 14),
      fetchFREDSeries('TLRESCONS', 14),
      fetchFREDSeries('PERMIT', 14),
      // Census BPS current and prior year periods
      fetchCensusPermits(getCensusPeriods().current),
      fetchCensusPermits(getCensusPeriods().prior),
    ]);

    // ---- Extract values with safe fallbacks ----
    const blsNational  = blsNationalResult.status  === 'fulfilled' ? blsNationalResult.value  : [];
    const msaRates     = blsMSAResult.status        === 'fulfilled' ? blsMSAResult.value       : new Map();
    const fedFundsObs  = fredFEDFUNDS.status        === 'fulfilled' ? fredFEDFUNDS.value       : [];
    const ppiInputsObs = fredWPUIP2311X1.status     === 'fulfilled' ? fredWPUIP2311X1.value    : [];
    const ppiSteelObs  = fredWPU101.status          === 'fulfilled' ? fredWPU101.value         : [];
    const ppiLumberObs = fredWPU0811.status         === 'fulfilled' ? fredWPU0811.value        : [];
    const ppiConcObs   = fredWPUID931.status        === 'fulfilled' ? fredWPUID931.value       : [];
    const tlresconsObs = fredTLRESCONS.status       === 'fulfilled' ? fredTLRESCONS.value      : [];
    const permitObs    = fredPERMIT.status          === 'fulfilled' ? fredPERMIT.value         : [];
    const censusNow    = censusCurrentResult.status === 'fulfilled' ? censusCurrentResult.value : new Map();
    const censusPrior  = censusPriorResult.status   === 'fulfilled' ? censusPriorResult.value   : new Map();

    // BLS national employment series
    const empTotalSeries = blsNational.find(s => s.seriesID === 'CEU2000000001');
    const ppiSteelBLS    = blsNational.find(s => s.seriesID === 'WPU101');
    const ppiConcBLS     = blsNational.find(s => s.seriesID === 'WPUID931');
    const ppiLumberBLS   = blsNational.find(s => s.seriesID === 'WPU0811');
    const ppiInputsBLS   = blsNational.find(s => s.seriesID === 'WPUIP2311X1');

    // Prefer FRED PPI data (slightly more current) with BLS fallback
    const steelYoY  = ppiSteelObs.length  >= 13 ? fredYoYChange(ppiSteelObs)  : (ppiSteelBLS  ? parsePPIYoYChange(ppiSteelBLS)  : 0);
    const concYoY   = ppiConcObs.length   >= 13 ? fredYoYChange(ppiConcObs)   : (ppiConcBLS   ? parsePPIYoYChange(ppiConcBLS)   : 0);
    const lumberYoY = ppiLumberObs.length >= 13 ? fredYoYChange(ppiLumberObs) : (ppiLumberBLS ? parsePPIYoYChange(ppiLumberBLS) : 0);
    const inputsYoY = ppiInputsObs.length >= 13 ? fredYoYChange(ppiInputsObs) : (ppiInputsBLS ? parsePPIYoYChange(ppiInputsBLS) : 0);

    // National construction employment (thousands) and MoM change
    let nationalEmpThousands = 8100;
    let nationalEmpChangePct = 0;
    if (empTotalSeries && empTotalSeries.data.length >= 2) {
      nationalEmpThousands = parseFloat(empTotalSeries.data[0].value);
      const prev = parseFloat(empTotalSeries.data[1].value);
      nationalEmpChangePct = prev > 0 ? ((nationalEmpThousands - prev) / prev) * 100 : 0;
    }

    // Derive national trade unemployment proxy
    // Construction trade unemployment = total const. employment growth inverted + baseline ~5%
    const nationalTradeUnemploymentRate = Math.max(3.0, 6.0 - nationalEmpChangePct * 0.5);

    // FRED rates
    const fedFunds = fredLatestValue(fedFundsObs) || 4.33;
    const tlresconsYoY = fredYoYChange(tlresconsObs);

    // FRED permit YoY for data strip
    const permitLatest = fredLatestValue(permitObs);
    const permitPrev   = permitObs.length >= 2 ? (parseFloat(permitObs[1].value) || 0) : 0;
    const permitMoMPct = permitPrev > 0 ? ((permitLatest - permitPrev) / permitPrev) * 100 : 0;

    // Collect signals from FRED that are meaningful for MPI
    const allSignals: SignalItem[] = [];
    const now = new Date().toISOString();

    if (Math.abs(steelYoY) > 2) {
      allSignals.push({
        id: `fred-steel-yoy-${currentYear}`,
        type: 'STEEL_PRICE_CHANGE',
        category: 'materials',
        severity: Math.abs(steelYoY) > 10 ? 'critical' : Math.abs(steelYoY) > 5 ? 'high' : 'medium',
        msaId: 'national',
        title: `Steel PPI ${steelYoY > 0 ? '▲' : '▼'} ${Math.abs(steelYoY).toFixed(1)}% YoY`,
        description: `Iron & steel products PPI moved ${steelYoY.toFixed(1)}% YoY. Structural steel and rebar costs typically track within 2-3 months.`,
        source: 'FRED / BLS — PPI Iron and Steel Mill Products (WPU101)',
        sourceTier: 1,
        url: 'https://fred.stlouisfed.org/series/WPU101',
        value: fredLatestValue(ppiSteelObs.length ? ppiSteelObs : []),
        unit: 'PPI Index 1982=100',
        changeFromBaseline: steelYoY,
        timestamp: now,
        classifiedBy: 'api',
        confidence: 0.99,
      });
    }

    if (Math.abs(concYoY) > 2) {
      allSignals.push({
        id: `fred-concrete-yoy-${currentYear}`,
        type: 'CONCRETE_PRICE_CHANGE',
        category: 'materials',
        severity: Math.abs(concYoY) > 8 ? 'high' : 'medium',
        msaId: 'national',
        title: `Concrete PPI ${concYoY > 0 ? '▲' : '▼'} ${Math.abs(concYoY).toFixed(1)}% YoY`,
        description: `Ready-mix concrete PPI ${concYoY > 0 ? 'increased' : 'decreased'} ${Math.abs(concYoY).toFixed(1)}% YoY. Lags cement/aggregate inputs by 1-2 months.`,
        source: 'FRED / BLS — PPI Ready-Mix Concrete (WPUID931)',
        sourceTier: 1,
        url: 'https://fred.stlouisfed.org/series/WPUID931',
        value: fredLatestValue(ppiConcObs.length ? ppiConcObs : []),
        unit: 'PPI Index 1982=100',
        changeFromBaseline: concYoY,
        timestamp: now,
        classifiedBy: 'api',
        confidence: 0.99,
      });
    }

    if (Math.abs(inputsYoY) > 1.5) {
      allSignals.push({
        id: `fred-inputs-ppi-yoy-${currentYear}`,
        type: 'MATERIAL_TARIFF_CHANGE',
        category: 'materials',
        severity: Math.abs(inputsYoY) > 6 ? 'high' : 'medium',
        msaId: 'national',
        title: `Construction Inputs PPI ${inputsYoY > 0 ? '▲' : '▼'} ${Math.abs(inputsYoY).toFixed(1)}% YoY`,
        description: `Composite PPI for construction inputs moved ${inputsYoY.toFixed(1)}% YoY. Best single proxy for overall construction cost escalation.`,
        source: 'FRED / BLS — PPI Inputs to Construction Industries (WPUIP2311X1)',
        sourceTier: 1,
        url: 'https://fred.stlouisfed.org/series/WPUIP2311X1',
        changeFromBaseline: inputsYoY,
        timestamp: now,
        classifiedBy: 'api',
        confidence: 0.99,
      });
    }

    if (fedFunds > 4.5) {
      allSignals.push({
        id: `fred-fedfunds-${currentYear}`,
        type: 'RATE_CHANGE',
        category: 'macro',
        severity: fedFunds > 5.5 ? 'high' : 'medium',
        msaId: 'national',
        title: `Fed Funds Rate: ${fedFunds.toFixed(2)}% — ${fedFunds > 5 ? 'elevated' : 'moderate'} rate environment`,
        description: `Federal Funds Rate at ${fedFunds.toFixed(2)}%. Construction loan proxy rate: ~${(fedFunds + 2.25).toFixed(2)}%. Every 1% increase adds ~$1.5-2.5/SF financing cost.`,
        source: 'Federal Reserve — FRED (FEDFUNDS)',
        sourceTier: 1,
        url: 'https://fred.stlouisfed.org/series/FEDFUNDS',
        value: fedFunds,
        unit: '%',
        timestamp: now,
        classifiedBy: 'api',
        confidence: 1.0,
      });
    }

    // ---- Assemble FetchedData bundle ----
    const fetchedData: FetchedData = {
      steelPPIYoY:                    steelYoY,
      concretePPIYoY:                 concYoY,
      lumberPPIYoY:                   lumberYoY,
      constructionInputsPPIYoY:       inputsYoY,
      nationalConstructionEmployment: nationalEmpThousands,
      nationalEmploymentChangePct:    nationalEmpChangePct,
      nationalTradeUnemploymentRate,
      fedFundsRate:                   fedFunds,
      constructionSpendingChangePct:  tlresconsYoY,
      msaUnemploymentRates:           msaRates,
      censusCurrentData:              censusNow,
      censusPriorData:                censusPrior,
      allSignals,
    };

    // ---- Compute MPI for each MSA ----
    const dashboard: DashboardMSAData[] = MSA_CATALOG.map(msa => {
      // MSA-specific signals = national signals (affect all markets)
      const msaSignals = allSignals.map(s => ({ ...s, msaId: msa.id }));

      const bundle: MPIInputBundle = {
        msaId:   msa.id,
        msaName: msa.fullName,
        materials:       assembleMaterialsInput(fetchedData),
        labor:           assembleLaborInput(msa.id, fetchedData, msaSignals),
        backlog:         assembleBacklogInput(msa, fetchedData, msaSignals),
        supplyChain:     assembleSupplyChainInput(fetchedData, msaSignals),
        financialDistress: assembleFinancialDistressInput(fetchedData, msaSignals),
        signals:         msaSignals,
        previousScore:   undefined, // trend vs prior run (requires persistence layer)
      };

      return buildDashboardEntry(msa, bundle, fetchedData);
    });

    // ---- Data strip values for dashboard header ----
    const dataStrip: DataStripValues = {
      ppiConstructionInputs: {
        value:     fredLatestValue(ppiInputsObs),
        changeYoY: inputsYoY,
      },
      ppiSteelMill: {
        value:     fredLatestValue(ppiSteelObs),
        changeYoY: steelYoY,
      },
      ppiReadyMixConcrete: {
        value:     fredLatestValue(ppiConcObs),
        changeYoY: concYoY,
      },
      constructionEmployment: {
        valueThousands: nationalEmpThousands,
        changeMoM:      nationalEmpChangePct,
      },
      buildingPermits: {
        valueThousands: permitLatest,
        changeMoM:      permitMoMPct,
      },
      fedFundsRate: {
        value:     fedFunds,
        unchanged: Math.abs(fredYoYChange(fedFundsObs)) < 0.1,
      },
    };

    const responsePayload = {
      data: dashboard,
      dataStrip,
      signals: allSignals,
      meta: {
        fetchedAt: new Date().toISOString(),
        msaCount:  dashboard.length,
        sources: [
          'Bureau of Labor Statistics Public Data API v2',
          'Federal Reserve Bank of St. Louis — FRED',
          'U.S. Census Bureau — Building Permits Survey',
        ],
        cacheHit: false,
      },
    };

    const body = JSON.stringify(responsePayload);
    await setCache(cacheKey, body, cacheTTL);

    return new Response(body, {
      headers: {
        'Content-Type': 'application/json',
        'X-Cache': 'MISS',
        'Cache-Control': 'public, max-age=600',
        'Access-Control-Allow-Origin': '*',
      },
    });

  } catch (error) {
    return new Response(
      JSON.stringify({
        data: null,
        error: error instanceof Error ? error.message : 'MPI orchestration failed',
        meta: { fetchedAt: new Date().toISOString(), cacheHit: false },
      }),
      {
        status: 503,
        headers: {
          'Content-Type': 'application/json',
          'Access-Control-Allow-Origin': '*',
        },
      }
    );
  }
}
