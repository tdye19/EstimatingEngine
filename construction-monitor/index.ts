// ============================================================
// Construction Monitor — Core Type Definitions
// ============================================================

// --- MSA (Metropolitan Statistical Area) ---
export interface MSA {
  id: string;           // FIPS code e.g. "19820" (Detroit-Warren-Dearborn)
  name: string;         // "Detroit-Warren-Dearborn, MI"
  shortName: string;    // "Detroit"
  lat: number;
  lng: number;
  state: string;
  population: number;
}

// --- Market Pressure Index ---
export interface MPIScore {
  msaId: string;
  msaName: string;
  score: number;          // 0-100
  tier: MPITier;
  trend: 'rising' | 'stable' | 'falling';
  trendDelta: number;     // score change vs 30 days ago
  components: MPIComponents;
  alerts: ConvergenceAlert[];
  lastUpdated: string;    // ISO timestamp
}

export type MPITier =
  | 'favorable'   // 0-30:  Green — competitive, stable
  | 'moderate'    // 31-55: Yellow — watch closely
  | 'elevated'    // 56-75: Orange — build contingency
  | 'critical';   // 76-100: Red — serious escalation risk

export interface MPIComponents {
  materialsCostTrend: ComponentScore;   // 30% weight
  laborAvailability: ComponentScore;    // 25% weight
  projectBacklog: ComponentScore;       // 20% weight
  supplyChainStress: ComponentScore;    // 15% weight
  financialDistress: ComponentScore;    // 10% weight
}

export interface ComponentScore {
  rawScore: number;       // 0-100 pre-weighted
  weightedScore: number;  // contribution to MPI total
  weight: number;         // e.g. 0.30
  trend: 'rising' | 'stable' | 'falling';
  signals: SignalItem[];  // what drove this score
  lastUpdated: string;
}

// --- Signals (atomic data points) ---
export interface SignalItem {
  id: string;
  type: SignalType;
  category: SignalCategory;
  severity: SignalSeverity;
  msaId: string;
  title: string;
  description: string;
  source: string;
  sourceTier: 1 | 2 | 3 | 4;
  url?: string;
  value?: number;           // numeric value if applicable
  unit?: string;            // "$", "%", "days", etc.
  changeFromBaseline?: number; // % deviation from 90d baseline
  geoLat?: number;
  geoLng?: number;
  timestamp: string;
  classifiedBy: 'keyword' | 'llm' | 'api';
  confidence: number;       // 0-1
}

export type SignalType =
  // Materials
  | 'STEEL_PRICE_CHANGE'
  | 'CONCRETE_PRICE_CHANGE'
  | 'LUMBER_PRICE_CHANGE'
  | 'CEMENT_SUPPLY_DISRUPTION'
  | 'AGGREGATE_SHORTAGE'
  | 'MATERIAL_TARIFF_CHANGE'
  // Labor
  | 'STRIKE_FILED'
  | 'STRIKE_ACTIVE'
  | 'WAGE_RATE_CHANGE'
  | 'CBA_EXPIRING'
  | 'LABOR_SHORTAGE'
  | 'LABOR_SURPLUS'
  | 'OSHA_ENFORCEMENT'
  // Project Activity
  | 'PERMIT_SURGE'
  | 'PERMIT_DECLINE'
  | 'MEGA_PROJECT_ANNOUNCED'
  | 'FEDERAL_AWARD_LARGE'
  | 'PROJECT_CANCELLATION'
  // Supply Chain
  | 'PORT_CONGESTION'
  | 'PLANT_CLOSURE'
  | 'LEAD_TIME_SPIKE'
  | 'SUPPLIER_DISTRESS'
  // Financial Distress
  | 'LIEN_FILING'
  | 'CONTRACTOR_BANKRUPTCY'
  | 'SURETY_CLAIM'
  | 'PAYMENT_DEFAULT'
  | 'CREDIT_DOWNGRADE'
  // Macro
  | 'RATE_CHANGE'
  | 'TARIFF_IMPOSED'
  | 'WEATHER_RISK'
  | 'REGULATORY_CHANGE';

export type SignalCategory =
  | 'materials'
  | 'labor'
  | 'project_activity'
  | 'supply_chain'
  | 'financial_distress'
  | 'macro';

export type SignalSeverity = 'critical' | 'high' | 'medium' | 'low' | 'info';

// --- Convergence Alert ---
export interface ConvergenceAlert {
  id: string;
  msaId: string;
  title: string;
  body: string;
  severity: SignalSeverity;
  signals: string[];          // SignalItem IDs that triggered this
  categories: SignalCategory[];
  estimatedCostImpact?: CostImpact;
  generatedAt: string;
  expiresAt: string;
  aiGenerated: boolean;
}

export interface CostImpact {
  tradeAffected: string;      // "Structural Concrete" | "Structural Steel" | "General"
  estimatedRangeLow: number;  // percentage e.g. 0.04 = 4%
  estimatedRangeHigh: number; // percentage e.g. 0.09 = 9%
  confidence: 'low' | 'medium' | 'high';
  basis: string;              // explanation of how estimated
}

// --- Temporal Baseline (Welford's algorithm state) ---
export interface TemporalBaseline {
  msaId: string;
  signalType: SignalType;
  month: number;      // 1-12
  dayOfWeek: number;  // 0-6
  count: number;      // number of observations
  mean: number;
  M2: number;         // sum of squared deviations (Welford's)
  variance: number;
  stdDev: number;
  lastUpdated: string;
}

export interface AnomalyResult {
  zScore: number;
  severity: 'normal' | 'low' | 'medium' | 'high' | 'critical';
  message: string;
  baseline: TemporalBaseline;
}

// --- RSS Feed Item ---
export interface FeedItem {
  id: string;
  title: string;
  summary: string;
  url: string;
  source: string;
  sourceTier: 1 | 2 | 3 | 4;
  publishedAt: string;
  fetchedAt: string;
  category: SignalCategory;
  severity?: SignalSeverity;
  confidence?: number;
  classifiedBy?: 'keyword' | 'llm';
  msaIds?: string[];    // which MSAs are affected
  geoLat?: number;
  geoLng?: number;
}

// --- BLS Data Structures ---
export interface BLSSeriesResult {
  seriesID: string;
  data: BLSDataPoint[];
}

export interface BLSDataPoint {
  year: string;
  period: string;   // "M01" through "M12"
  periodName: string;
  value: string;
  footnotes: object[];
}

// --- Edge Function Response Shape ---
export interface EdgeResponse<T> {
  data: T | null;
  error: string | null;
  cached: boolean;
  fetchedAt: string;
  source: string;
  stale: boolean;
}
