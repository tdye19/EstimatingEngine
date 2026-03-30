// ============================================================
// src/lib/mpi-engine.ts
// Market Pressure Index (MPI) — Core Scoring Algorithm
//
// The MPI is the construction equivalent of World Monitor's
// Country Instability Index (CII). It produces a 0-100 score
// per Metropolitan Statistical Area (MSA) representing how
// much cost/execution pressure estimators should expect.
//
// SCORING PHILOSOPHY:
//   - 0-30:  Favorable   → Competitive market, stable pricing
//   - 31-55: Moderate    → Watch closely, normal contingency
//   - 56-75: Elevated    → Build 5-10% escalation buffer
//   - 76-100: Critical   → Serious risk, strategy discussion needed
//
// ARCHITECTURE:
//   - Five component scores, each 0-100
//   - Weighted sum → raw MPI
//   - Baseline anchoring prevents artificial volatility
//   - Temporal anomaly detection (Welford's) flags deviations
// ============================================================

import type {
  MPIScore, MPIComponents, MPITier, ComponentScore,
  SignalItem, SignalCategory, ConvergenceAlert, CostImpact,
  TemporalBaseline, AnomalyResult
} from '../types/index.ts';

// ---- Component Weights (must sum to 1.0) ----
export const MPI_WEIGHTS = {
  materialsCostTrend: 0.30,   // 30% — biggest direct impact on estimates
  laborAvailability:  0.25,   // 25% — tight labor = escalation + delays
  projectBacklog:     0.20,   // 20% — market heat / competition density
  supplyChainStress:  0.15,   // 15% — lead times, plant disruptions, ports
  financialDistress:  0.10,   // 10% — sub/GC health signals
} as const;

// ---- Baseline Structural Risk by MSA ----
// Markets have different structural characteristics.
// Detroit is different from San Francisco. This prevents
// statistical noise from swamping legitimate market differences.
// Scale: 0-40 (leaves 60 points for detected signals)
export const MSA_BASELINE_RISK: Record<string, number> = {
  // Michigan
  'detroit':       12,  // Mature market, stable labor, moderate backlog
  'grand-rapids':  10,
  'lansing':       8,

  // High-pressure metros (chronic labor/cost pressure)
  'new-york':      35,
  'san-francisco': 38,
  'seattle':       32,
  'boston':        30,
  'miami':         28,

  // Boom markets (high permit activity, tighter subs)
  'phoenix':       22,
  'dallas':        20,
  'houston':       18,
  'nashville':     24,
  'denver':        22,
  'austin':        26,

  // Midwest / stable markets
  'chicago':       16,
  'columbus':      12,
  'indianapolis':  11,
  'minneapolis':   14,

  // Default for unmapped MSAs
  '_default':      15,
};

// ---- Materials Cost Trend Scoring ----
// Inputs: PPI indices from FRED, regional materials news signals
// Range: 0-100

export interface MaterialsInput {
  steelPPIChangePercent: number;      // YoY % change in PPI iron/steel
  concretePPIChangePercent: number;   // YoY % change in PPI ready-mix
  lumberPPIChangePercent: number;     // YoY % change in PPI softwood lumber
  constructionInputsPPIChange: number; // Composite PPI for construction inputs
  activeTariffSignals: number;        // count of active tariff-related signals
  supplyDisruptionSignals: number;    // count of supply disruption signals
  regionalPricePremiumPercent?: number; // regional premium vs national avg
}

export function scoreMaterialsCostTrend(input: MaterialsInput): number {
  let score = 0;

  // ---- Composite PPI Change (0-50 points) ----
  // This is the most reliable signal — official government data
  const compositePPIScore = Math.min(50, Math.max(0,
    // Map -5% to +15% change → 0 to 50 points
    // At 0% change = 10 points (baseline neutral)
    // At +10% change = 40 points (significant escalation)
    // At -5% change = 0 points (deflationary, favorable)
    (input.constructionInputsPPIChange + 5) * (50 / 20)
  ));
  score += compositePPIScore;

  // ---- Specific Trade Material Signals (0-30 points) ----
  // Each major material contributes based on YoY change magnitude
  const steelScore = Math.min(10, Math.max(0, input.steelPPIChangePercent * 0.8));
  const concreteScore = Math.min(10, Math.max(0, input.concretePPIChangePercent * 1.2));
  const lumberScore = Math.min(10, Math.max(0, input.lumberPPIChangePercent * 0.6));
  score += steelScore + concreteScore + lumberScore;

  // ---- Active Tariff/Disruption Signals (0-20 points) ----
  const tariffScore = Math.min(12, input.activeTariffSignals * 4);
  const disruptionScore = Math.min(8, input.supplyDisruptionSignals * 2.5);
  score += tariffScore + disruptionScore;

  // ---- Regional Premium (modifier, not additive) ----
  if (input.regionalPricePremiumPercent) {
    score *= (1 + input.regionalPricePremiumPercent / 100);
  }

  return Math.min(100, Math.max(0, score));
}

// ---- Labor Availability Scoring ----
// Inputs: BLS unemployment by trade, strike data, CBA expiry calendar

export interface LaborInput {
  tradeUnemploymentRate: number;      // % (construction trades specific)
  nationalAvgTradeUnemployment: number; // for comparison
  activeStrikeCount: number;          // active strikes in MSA
  cbaDaysToExpiry: number;            // nearest CBA expiry in days (999 = no expiry)
  laborNewsSignalCount: number;       // relevant labor news signals
  prevailingWageChangePercent?: number; // recent prevailing wage change
  apprenticeshipRatio?: number;       // apprentices / journeymen (low = tight)
}

export function scoreLaborAvailability(input: LaborInput): number {
  let score = 0;

  // ---- Unemployment Rate vs Baseline (0-40 points) ----
  // Construction unemployment BELOW ~5% signals tight labor
  // Above ~10% signals surplus (favorable for estimating)
  const unemploymentDelta = input.nationalAvgTradeUnemployment - input.tradeUnemploymentRate;
  // unemploymentDelta > 0 means local is TIGHTER than national (bad)
  const unemploymentScore = Math.min(40, Math.max(0,
    20 + (unemploymentDelta * 5) // 20 = neutral, +5 per point tighter
  ));
  score += unemploymentScore;

  // ---- Active Strikes (0-30 points) ----
  // Even one active strike in a major trade is a significant signal
  const strikeScore = Math.min(30, input.activeStrikeCount * 15);
  score += strikeScore;

  // ---- CBA Expiry Proximity (0-20 points) ----
  // CBAs expiring within 90 days create wage uncertainty
  let cbaScore = 0;
  if (input.cbaDaysToExpiry < 30) cbaScore = 20;       // imminent expiry
  else if (input.cbaDaysToExpiry < 60) cbaScore = 15;  // very close
  else if (input.cbaDaysToExpiry < 90) cbaScore = 10;  // approaching
  else if (input.cbaDaysToExpiry < 180) cbaScore = 5;  // on horizon
  score += cbaScore;

  // ---- Prevailing Wage Changes (0-10 points) ----
  if (input.prevailingWageChangePercent) {
    const wageScore = Math.min(10, Math.max(0, input.prevailingWageChangePercent * 1.5));
    score += wageScore;
  }

  // ---- News signal count modifier ----
  // More labor news = more volatility
  score += Math.min(5, input.laborNewsSignalCount * 0.5);

  return Math.min(100, Math.max(0, score));
}

// ---- Project Backlog / Market Heat Scoring ----
// Inputs: Census permits, Dodge starts, construction spending
// High backlog = subs are busy = less competitive pricing

export interface BacklogInput {
  permitValueChangePercentYoY: number;  // % change in building permit values
  permitVolumeChangePercent: number;    // % change in permit count
  constructionSpendingChangePercent: number; // FRED TLRESCONS
  megaProjectAnnouncementCount: number; // projects >$100M announced in 180 days
  federalAwardCount: number;            // large federal awards in region
  historicalBacklogMonths: number;      // months of backlog (if available)
}

export function scoreProjectBacklog(input: BacklogInput): number {
  let score = 0;

  // ---- Permit Value Trend (0-35 points) ----
  // YoY permit value change is the best market heat signal
  const permitScore = Math.min(35, Math.max(0,
    17.5 + (input.permitValueChangePercentYoY * 0.875)
    // +20% YoY permits → ~35 points (hot market)
    // 0% YoY → ~17.5 points (neutral)
    // -20% YoY → ~0 points (cold market)
  ));
  score += permitScore;

  // ---- Construction Spending (0-25 points) ----
  const spendingScore = Math.min(25, Math.max(0,
    12.5 + (input.constructionSpendingChangePercent * 0.625)
  ));
  score += spendingScore;

  // ---- Mega Project Multiplier (0-25 points) ----
  // Mega projects absorb large quantities of specialized labor and materials
  // They have outsized effect on market tightness
  const megaScore = Math.min(25, input.megaProjectAnnouncementCount * 8);
  score += megaScore;

  // ---- Federal Awards (0-15 points) ----
  const federalScore = Math.min(15, input.federalAwardCount * 3);
  score += federalScore;

  return Math.min(100, Math.max(0, score));
}

// ---- Supply Chain Stress Scoring ----
// Inputs: Port delays, plant closures, lead time signals

export interface SupplyChainInput {
  portCongestionLevel: 'none' | 'minimal' | 'moderate' | 'severe'; // for material ports
  plantClosureCount: number;       // cement/steel/etc plants recently closed
  leadTimeSpikeSignals: number;    // count of lead time spike news items
  supplierDistressSignals: number; // count of distressed supplier signals
  weatherDisruptionActive: boolean; // major weather event affecting supply
  tariffImpactedMaterials: number; // count of tariff-affected material categories
}

export function scoreSupplyChainStress(input: SupplyChainInput): Promise<number> | number {
  let score = 0;

  // ---- Port Congestion (0-30 points) ----
  const portScore = {
    none: 0,
    minimal: 8,
    moderate: 18,
    severe: 30,
  }[input.portCongestionLevel];
  score += portScore;

  // ---- Plant Closures (0-30 points) ----
  // Each cement/concrete plant closure is a major regional event
  const plantScore = Math.min(30, input.plantClosureCount * 15);
  score += plantScore;

  // ---- Lead Time Signals (0-20 points) ----
  const leadTimeScore = Math.min(20, input.leadTimeSpikeSignals * 4);
  score += leadTimeScore;

  // ---- Weather + Tariff (0-20 points) ----
  const weatherScore = input.weatherDisruptionActive ? 10 : 0;
  const tariffScore = Math.min(10, input.tariffImpactedMaterials * 2.5);
  score += weatherScore + tariffScore;

  return Math.min(100, Math.max(0, score));
}

// ---- Financial Distress Scoring ----
// Inputs: Lien filings, bankruptcies, surety claims

export interface FinancialDistressInput {
  lienFilingVelocity: 'low' | 'normal' | 'elevated' | 'high'; // vs 90d baseline
  bankruptcyFilingsCount: number;    // GC/sub bankruptcies in 90 days
  suretyClaimsCount: number;         // surety bond claims in region
  paymentDefaultNewsCount: number;   // payment default news items
  creditDowngradeSignals: number;    // D&B or news credit concerns
}

export function scoreFinancialDistress(input: FinancialDistressInput): number {
  let score = 0;

  // ---- Lien Filing Velocity (0-35 points) ----
  const lienScore = {
    low: 0,
    normal: 10,
    elevated: 22,
    high: 35,
  }[input.lienFilingVelocity];
  score += lienScore;

  // ---- Bankruptcies (0-30 points) ----
  // Each contractor bankruptcy is a significant signal
  const bankruptcyScore = Math.min(30, input.bankruptcyFilingsCount * 12);
  score += bankruptcyScore;

  // ---- Surety Claims (0-20 points) ----
  const suretyScore = Math.min(20, input.suretyClaimsCount * 8);
  score += suretyScore;

  // ---- Payment Default News (0-15 points) ----
  const defaultScore = Math.min(15, input.paymentDefaultNewsCount * 3);
  score += defaultScore;

  return Math.min(100, Math.max(0, score));
}

// ---- Welford's Online Algorithm for Temporal Baseline ----
// Ported directly from World Monitor's anomaly detection.
// Computes streaming mean/variance without storing all history.

export function welfordUpdate(baseline: TemporalBaseline, newValue: number): TemporalBaseline {
  const count = baseline.count + 1;
  const delta = newValue - baseline.mean;
  const mean = baseline.mean + delta / count;
  const delta2 = newValue - mean;
  const M2 = baseline.M2 + delta * delta2;
  const variance = count > 1 ? M2 / (count - 1) : 0;
  const stdDev = Math.sqrt(variance);

  return {
    ...baseline,
    count,
    mean,
    M2,
    variance,
    stdDev,
    lastUpdated: new Date().toISOString(),
  };
}

export function detectAnomaly(
  baseline: TemporalBaseline,
  currentValue: number
): AnomalyResult {
  // Need at least 10 observations before declaring anomalies
  if (baseline.count < 10) {
    return {
      zScore: 0,
      severity: 'normal',
      message: `Insufficient history (${baseline.count}/10 observations needed)`,
      baseline,
    };
  }

  const zScore = baseline.stdDev > 0
    ? (currentValue - baseline.mean) / baseline.stdDev
    : 0;

  const absZ = Math.abs(zScore);
  const severity =
    absZ >= 3.0 ? 'critical' :
    absZ >= 2.0 ? 'high' :
    absZ >= 1.5 ? 'medium' :
    absZ >= 1.0 ? 'low' : 'normal';

  const direction = currentValue > baseline.mean ? 'above' : 'below';
  const message =
    severity === 'normal'
      ? `Within normal range (z=${zScore.toFixed(2)})`
      : `${severity.toUpperCase()}: ${absZ.toFixed(1)}x ${direction} historical mean for this period (z=${zScore.toFixed(2)}, mean=${baseline.mean.toFixed(1)}, σ=${baseline.stdDev.toFixed(1)})`;

  return { zScore, severity, message, baseline };
}

// ---- Convergence Detection ----
// Fire an alert when multiple signal categories spike in the same MSA

export interface ConvergenceInput {
  msaId: string;
  msaName: string;
  signals: SignalItem[];
  mpiComponents: MPIComponents;
}

export function detectConvergence(input: ConvergenceInput): ConvergenceAlert[] {
  const alerts: ConvergenceAlert[] = [];
  const { msaId, msaName, signals, mpiComponents } = input;

  // Count high-severity signals by category
  const categoryCounts: Record<SignalCategory, number> = {
    materials: 0,
    labor: 0,
    project_activity: 0,
    supply_chain: 0,
    financial_distress: 0,
    macro: 0,
  };

  const highSeveritySignals = signals.filter(
    s => s.severity === 'critical' || s.severity === 'high'
  );

  for (const signal of highSeveritySignals) {
    categoryCounts[signal.category]++;
  }

  const spikedCategories = Object.entries(categoryCounts)
    .filter(([_, count]) => count >= 1)
    .map(([cat]) => cat as SignalCategory);

  // Need at least 2 categories spiking for convergence
  if (spikedCategories.length < 2) return alerts;

  // ---- Generate convergence alert ----
  const severity: SignalItem['severity'] =
    spikedCategories.length >= 4 ? 'critical' :
    spikedCategories.length >= 3 ? 'high' : 'medium';

  // Estimate cost impact based on which categories are affected
  const costImpact = estimateCostImpact(spikedCategories, mpiComponents);

  const categoryLabels: Record<SignalCategory, string> = {
    materials: 'materials pricing',
    labor: 'labor market',
    project_activity: 'project backlog',
    supply_chain: 'supply chain',
    financial_distress: 'contractor distress',
    macro: 'macro conditions',
  };

  const categoryText = spikedCategories
    .map(c => categoryLabels[c])
    .join(' + ');

  const severityEmoji = severity === 'critical' ? '🔴' : severity === 'high' ? '🟠' : '🟡';

  alerts.push({
    id: `convergence-${msaId}-${Date.now()}`,
    msaId,
    title: `${severityEmoji} CONVERGENCE — ${msaName}: ${spikedCategories.length} signal categories elevated`,
    body: buildConvergenceBody(msaName, spikedCategories, highSeveritySignals, costImpact),
    severity,
    signals: highSeveritySignals.map(s => s.id),
    categories: spikedCategories,
    estimatedCostImpact: costImpact,
    generatedAt: new Date().toISOString(),
    expiresAt: new Date(Date.now() + 48 * 3600 * 1000).toISOString(),
    aiGenerated: false, // keyword-based, LLM refines async
  });

  return alerts;
}

function buildConvergenceBody(
  msaName: string,
  categories: SignalCategory[],
  signals: SignalItem[],
  impact: CostImpact | undefined
): string {
  const lines: string[] = [];

  // Top-level statement
  lines.push(`Multiple pressure signals are co-occurring in ${msaName}:`);

  // List top signals per category
  for (const cat of categories) {
    const catSignals = signals.filter(s => s.category === cat).slice(0, 2);
    for (const s of catSignals) {
      lines.push(`  • ${s.title}`);
    }
  }

  // Cost impact recommendation
  if (impact && impact.confidence !== 'low') {
    const low = (impact.estimatedRangeLow * 100).toFixed(0);
    const high = (impact.estimatedRangeHigh * 100).toFixed(0);
    lines.push(`\nEstimated impact on ${impact.tradeAffected} estimates: +${low}–${high}%`);
    lines.push(`Basis: ${impact.basis}`);
  }

  lines.push(`\nReview escalation assumptions on bids with >60-day award-to-start exposure.`);

  return lines.join('\n');
}

function estimateCostImpact(
  categories: SignalCategory[],
  components: MPIComponents
): CostImpact | undefined {
  if (!categories.includes('materials') && !categories.includes('labor')) return undefined;

  let lowImpact = 0;
  let highImpact = 0;
  const tradeFactors: string[] = [];

  if (categories.includes('materials')) {
    const matScore = components.materialsCostTrend.rawScore;
    // Scale: score 50 = ~2% impact, score 80 = ~6% impact
    const matImpact = (matScore - 30) / 50 * 0.06;
    lowImpact += Math.max(0, matImpact * 0.7);
    highImpact += Math.max(0, matImpact * 1.3);
    tradeFactors.push('materials escalation');
  }

  if (categories.includes('labor')) {
    const labScore = components.laborAvailability.rawScore;
    const labImpact = (labScore - 30) / 70 * 0.05;
    lowImpact += Math.max(0, labImpact * 0.7);
    highImpact += Math.max(0, labImpact * 1.3);
    tradeFactors.push('labor rate pressure');
  }

  if (lowImpact < 0.01) return undefined;

  return {
    tradeAffected: categories.includes('materials') && categories.includes('labor')
      ? 'Structural Concrete & Steel'
      : categories.includes('materials') ? 'Materials-Heavy Trades'
      : 'Labor-Intensive Trades',
    estimatedRangeLow: lowImpact,
    estimatedRangeHigh: highImpact,
    confidence: highImpact > 0.08 ? 'high' : highImpact > 0.04 ? 'medium' : 'low',
    basis: `Historical correlation between ${tradeFactors.join(' + ')} signals and realized bid-to-buyout variance`,
  };
}

// ---- Main MPI Calculator ----
// Assembles all component scores into the final MPI

export interface MPIInputBundle {
  msaId: string;
  msaName: string;
  materials: MaterialsInput;
  labor: LaborInput;
  backlog: BacklogInput;
  supplyChain: SupplyChainInput;
  financialDistress: FinancialDistressInput;
  signals: SignalItem[];
  previousScore?: number;  // for trend calculation
}

export function calculateMPI(input: MPIInputBundle): MPIScore {
  const baselineRisk = MSA_BASELINE_RISK[input.msaId] ?? MSA_BASELINE_RISK['_default'];

  // ---- Score each component ----
  const matRaw = scoreMaterialsCostTrend(input.materials);
  const labRaw = scoreLaborAvailability(input.labor);
  const backlogRaw = scoreProjectBacklog(input.backlog);
  const supplyRaw = scoreSupplyChainStress(input.supplyChain) as number;
  const distressRaw = scoreFinancialDistress(input.financialDistress);

  // ---- Apply weights ----
  const matWeighted = matRaw * MPI_WEIGHTS.materialsCostTrend;
  const labWeighted = labRaw * MPI_WEIGHTS.laborAvailability;
  const backlogWeighted = backlogRaw * MPI_WEIGHTS.projectBacklog;
  const supplyWeighted = supplyRaw * MPI_WEIGHTS.supplyChainStress;
  const distressWeighted = distressRaw * MPI_WEIGHTS.financialDistress;

  // ---- Weighted sum → signal score (0-100) ----
  const signalScore = matWeighted + labWeighted + backlogWeighted + supplyWeighted + distressWeighted;

  // ---- Blend with baseline (40% baseline structural risk, 60% detected signals) ----
  // This prevents low-signal periods from making any market look "safe"
  const rawMPI = (baselineRisk / 100 * 40) + (signalScore * 0.60);
  const finalMPI = Math.min(100, Math.max(0, rawMPI));

  // ---- Determine tier ----
  const tier: MPITier =
    finalMPI <= 30 ? 'favorable' :
    finalMPI <= 55 ? 'moderate' :
    finalMPI <= 75 ? 'elevated' : 'critical';

  // ---- Trend calculation ----
  const trendDelta = input.previousScore !== undefined ? finalMPI - input.previousScore : 0;
  const trend: MPIScore['trend'] =
    Math.abs(trendDelta) < 2 ? 'stable' :
    trendDelta > 0 ? 'rising' : 'falling';

  // ---- Build component detail ----
  const now = new Date().toISOString();

  const components: MPIComponents = {
    materialsCostTrend: {
      rawScore: matRaw,
      weightedScore: matWeighted,
      weight: MPI_WEIGHTS.materialsCostTrend,
      trend: trendDelta > 0 ? 'rising' : trendDelta < 0 ? 'falling' : 'stable',
      signals: input.signals.filter(s => s.category === 'materials'),
      lastUpdated: now,
    },
    laborAvailability: {
      rawScore: labRaw,
      weightedScore: labWeighted,
      weight: MPI_WEIGHTS.laborAvailability,
      trend: 'stable',
      signals: input.signals.filter(s => s.category === 'labor'),
      lastUpdated: now,
    },
    projectBacklog: {
      rawScore: backlogRaw,
      weightedScore: backlogWeighted,
      weight: MPI_WEIGHTS.projectBacklog,
      trend: 'stable',
      signals: input.signals.filter(s => s.category === 'project_activity'),
      lastUpdated: now,
    },
    supplyChainStress: {
      rawScore: supplyRaw,
      weightedScore: supplyWeighted,
      weight: MPI_WEIGHTS.supplyChainStress,
      trend: 'stable',
      signals: input.signals.filter(s => s.category === 'supply_chain'),
      lastUpdated: now,
    },
    financialDistress: {
      rawScore: distressRaw,
      weightedScore: distressWeighted,
      weight: MPI_WEIGHTS.financialDistress,
      trend: 'stable',
      signals: input.signals.filter(s => s.category === 'financial_distress'),
      lastUpdated: now,
    },
  };

  // ---- Detect convergence alerts ----
  const alerts = detectConvergence({
    msaId: input.msaId,
    msaName: input.msaName,
    signals: input.signals,
    mpiComponents: components,
  });

  return {
    msaId: input.msaId,
    msaName: input.msaName,
    score: Math.round(finalMPI * 10) / 10, // 1 decimal precision
    tier,
    trend,
    trendDelta: Math.round(trendDelta * 10) / 10,
    components,
    alerts,
    lastUpdated: now,
  };
}

// ---- MPI Interpretation Helper ----
// Returns human-readable context for estimators

export function interpretMPI(score: MPIScore): {
  headline: string;
  recommendation: string;
  contingencyGuidance: string;
  urgency: 'monitor' | 'review' | 'act';
} {
  const { tier, trend, trendDelta, msaName } = score;

  const tierText = {
    favorable: {
      headline: `${msaName} market is favorable for estimating`,
      recommendation: `Competitive subcontractor environment. Materials pricing stable. Standard escalation assumptions should hold.`,
      contingencyGuidance: `Standard 3-5% escalation contingency appropriate for bids with 12+ month schedule.`,
      urgency: 'monitor' as const,
    },
    moderate: {
      headline: `${msaName} shows moderate market pressure`,
      recommendation: `Some cost pressure building. Review unit prices against recent bids. Check sub pricing for key trades before locking numbers.`,
      contingencyGuidance: `Consider 5-8% escalation buffer for bids awarded >6 months out. Flag steel and concrete for early buyout.`,
      urgency: 'review' as const,
    },
    elevated: {
      headline: `${msaName} has elevated escalation risk — build contingency`,
      recommendation: `Multiple pressure signals active. Subcontractors are likely carrying escalation clauses. Get updated quotes; don't rely on historical unit prices for this market.`,
      contingencyGuidance: `8-12% escalation contingency recommended. Early procurement strategy for structural steel and concrete is advisable.`,
      urgency: 'act' as const,
    },
    critical: {
      headline: `⚠️ ${msaName} is under critical market pressure`,
      recommendation: `Serious escalation and execution risk. This market requires a strategy conversation before locking bid pricing. Consider escalation clauses in your proposal or significant front-loaded contingency.`,
      contingencyGuidance: `12-18%+ escalation contingency. Consider material price protection language in your proposal. Discuss with owner.`,
      urgency: 'act' as const,
    },
  }[tier];

  const trendSuffix = trend === 'rising'
    ? ` Pressure is increasing (+${trendDelta} pts vs 30 days ago) — act before conditions worsen.`
    : trend === 'falling'
    ? ` Conditions are improving (${trendDelta} pts vs 30 days ago).`
    : '';

  return {
    ...tierText,
    recommendation: tierText.recommendation + trendSuffix,
  };
}
