"""Pydantic v2 schemas for API request/response validation."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


# --- Base ---
class APIResponse(BaseModel):
    success: bool = True
    message: str = ""
    data: dict | list | None = None
    error: str | None = None


# --- Chunked Upload ---
class ChunkedUploadInitRequest(BaseModel):
    filename: str
    file_size: int
    content_type: str = "application/octet-stream"


# --- Organization ---
class OrganizationCreate(BaseModel):
    name: str
    address: str | None = None
    phone: str | None = None
    license_number: str | None = None


class OrganizationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    address: str | None = None
    phone: str | None = None
    license_number: str | None = None
    created_at: datetime


# --- User ---
class UserCreate(BaseModel):
    email: str
    password: str
    full_name: str
    role: str = "estimator"
    organization_id: int | None = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    full_name: str
    role: str
    organization_id: int | None = None


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut | None = None


# --- Project ---
class ProjectCreate(BaseModel):
    name: str
    project_number: str | None = None
    project_type: str = "commercial"
    mode: str = "shadow"
    description: str | None = None
    location: str | None = None
    square_footage: float | None = None
    estimated_value: float | None = None
    bid_date: str | None = None
    trade_focus: str | None = None
    scope_type: str | None = None
    client_name: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None
    project_type: str | None = None
    status: str | None = None
    mode: str | None = None
    description: str | None = None
    location: str | None = None
    square_footage: float | None = None
    estimated_value: float | None = None
    bid_date: str | None = None
    manual_estimate_total: float | None = None
    manual_estimate_notes: str | None = None
    trade_focus: str | None = None
    scope_type: str | None = None
    client_name: str | None = None


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    project_number: str
    project_type: str
    status: str
    mode: str = "shadow"
    description: str | None = None
    location: str | None = None
    square_footage: float | None = None
    estimated_value: float | None = None
    bid_date: str | None = None
    manual_estimate_total: float | None = None
    manual_estimate_notes: str | None = None
    trade_focus: str | None = None
    scope_type: str | None = None
    client_name: str | None = None
    created_at: datetime
    updated_at: datetime


class ShadowComparisonOut(BaseModel):
    project_id: int
    mode: str
    apex_estimate_total: float | None = None
    manual_estimate_total: float | None = None
    manual_estimate_notes: str | None = None
    variance_absolute: float | None = None
    variance_pct: float | None = None
    by_division: list | None = None


# --- Document ---
class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    filename: str
    file_type: str
    classification: str | None = None
    file_size_bytes: int | None = None
    page_count: int | None = None
    processing_status: str
    created_at: datetime


# --- Spec Section ---
class SpecSectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    document_id: int
    division_number: str
    section_number: str
    title: str
    work_description: str | None = None
    materials_referenced: list | None = None
    execution_requirements: str | None = None
    submittal_requirements: str | None = None
    keywords: list | None = None
    assembly_parameters_json: dict | None = None  # Sprint 18.2 — Division 03 only


# --- Gap Report ---
class GapReportItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    division_number: str
    section_number: str | None = None
    title: str
    gap_type: str
    severity: str
    description: str | None = None
    recommendation: str | None = None
    risk_score: float | None = None


class GapReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    overall_score: float | None = None
    total_gaps: int
    critical_count: int
    moderate_count: int
    watch_count: int
    summary: str | None = None
    items: list[GapReportItemOut] = []
    created_at: datetime


# --- Takeoff ---
class TakeoffItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    spec_section_id: int | None = None
    csi_code: str
    description: str
    quantity: float
    unit_of_measure: str
    drawing_reference: str | None = None
    confidence: float
    notes: str | None = None
    is_manual_override: int


class TakeoffItemUpdate(BaseModel):
    description: str | None = None
    quantity: float | None = None
    unit_of_measure: str | None = None
    notes: str | None = None


# --- Labor Estimate ---
class LaborEstimateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    takeoff_item_id: int
    csi_code: str
    work_type: str | None = None
    crew_type: str | None = None
    productivity_rate: float
    quantity: float
    labor_hours: float
    crew_size: int
    crew_days: float | None = None
    hourly_rate: float
    total_labor_cost: float


# --- Estimate ---
class EstimateLineItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    division_number: str
    csi_code: str
    description: str
    quantity: float
    unit_of_measure: str
    labor_cost: float
    material_cost: float
    equipment_cost: float
    subcontractor_cost: float
    total_cost: float
    unit_cost: float


class EstimateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    version: int
    status: str
    total_direct_cost: float
    total_labor_cost: float
    total_material_cost: float
    total_subcontractor_cost: float
    gc_markup_pct: float
    gc_markup_amount: float
    overhead_pct: float
    overhead_amount: float
    profit_pct: float
    profit_amount: float
    contingency_pct: float
    contingency_amount: float
    total_bid_amount: float
    exclusions: list | None = None
    assumptions: list | None = None
    alternates: list | None = None
    executive_summary: str | None = None
    bid_bond_required: int
    line_items: list[EstimateLineItemOut] = []
    created_at: datetime


# --- Actuals & Variance ---
class ProjectActualOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    csi_code: str
    description: str | None = None
    estimated_quantity: float | None = None
    actual_quantity: float | None = None
    estimated_labor_hours: float | None = None
    actual_labor_hours: float | None = None
    estimated_cost: float | None = None
    actual_cost: float | None = None
    variance_hours: float | None = None
    variance_cost: float | None = None
    variance_pct: float | None = None


class VarianceReportOut(BaseModel):
    project_id: int
    total_items: int
    overall_variance_pct: float | None = None
    accuracy_score: float | None = None
    items: list[ProjectActualOut] = []
    by_division: dict | None = None


# --- Productivity ---
class ProductivityHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    csi_code: str
    work_type: str
    crew_type: str | None = None
    productivity_rate: float
    unit_of_measure: str
    source_project: str | None = None
    is_actual: int
    confidence_score: float
    sample_count: int


class ProductivityUpdate(BaseModel):
    productivity_rate: float | None = None
    crew_type: str | None = None
    notes: str | None = None


# --- Equipment Rate ---
class EquipmentRateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    division_number: str
    csi_code: str | None = None
    equipment_pct: float
    description: str | None = None
    region: str | None = None
    created_at: datetime
    updated_at: datetime


class EquipmentRateCreate(BaseModel):
    division_number: str
    csi_code: str | None = None
    equipment_pct: float
    description: str | None = None
    region: str | None = None


class EquipmentRateUpdate(BaseModel):
    division_number: str | None = None
    csi_code: str | None = None
    equipment_pct: float | None = None
    description: str | None = None
    region: str | None = None


# --- Estimate Markup ---
class EstimateMarkupUpdate(BaseModel):
    overhead_pct: float | None = None
    profit_pct: float | None = None
    contingency_pct: float | None = None
    gc_markup_pct: float | None = None


# --- Pipeline Status ---
class AgentStepStatus(BaseModel):
    agent_number: int
    agent_name: str
    status: str  # pending / running / completed / failed / skipped
    started_at: str | None = None
    completed_at: str | None = None
    duration_seconds: float | None = None
    error_message: str | None = None
    output_summary: str | None = None


class PipelineStatusOut(BaseModel):
    project_id: int
    agents: list[AgentStepStatus]
    overall: str  # pending / running / completed / failed


# --- Bid Comparison ---
class BidComparisonItemCreate(BaseModel):
    division_number: str
    csi_code: str | None = None
    description: str | None = None
    amount: float = 0.0
    unit_cost: float | None = None
    quantity: float | None = None
    unit_of_measure: str | None = None
    notes: str | None = None


class BidComparisonItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    comparison_id: int
    division_number: str
    csi_code: str | None = None
    description: str | None = None
    amount: float
    unit_cost: float | None = None
    quantity: float | None = None
    unit_of_measure: str | None = None
    notes: str | None = None


class BidComparisonCreate(BaseModel):
    name: str
    source_type: str = "competitor"
    bid_date: str | None = None
    total_bid_amount: float | None = None
    notes: str | None = None
    items: list[BidComparisonItemCreate] = []


class BidComparisonOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    name: str
    source_type: str
    bid_date: str | None = None
    total_bid_amount: float | None = None
    notes: str | None = None
    items: list[BidComparisonItemOut] = []
    created_at: datetime


# --- Change Order ---
class ChangeOrderCreate(BaseModel):
    title: str
    description: str | None = None
    csi_code: str | None = None
    change_type: str = "addition"
    requested_by: str | None = None
    cost_impact: float = 0.0
    schedule_impact_days: int = 0
    status: str = "pending"


class ChangeOrderUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    csi_code: str | None = None
    change_type: str | None = None
    requested_by: str | None = None
    cost_impact: float | None = None
    schedule_impact_days: int | None = None
    status: str | None = None


class ChangeOrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    co_number: str
    title: str
    description: str | None = None
    csi_code: str | None = None
    change_type: str
    requested_by: str | None = None
    cost_impact: float
    schedule_impact_days: int
    status: str
    approved_by: str | None = None
    approved_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


# --- Estimate Version ---
class EstimateVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    version: int
    status: str
    total_direct_cost: float
    total_bid_amount: float
    created_at: datetime


# --- Agent Run Log ---
class AgentRunLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    agent_name: str
    agent_number: int
    status: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_seconds: float | None = None
    tokens_used: int | None = None
    output_summary: str | None = None
    error_message: str | None = None


# --- User Update (Admin) ---
class UserUpdate(BaseModel):
    full_name: str | None = None
    role: str | None = None
    is_active: bool | None = None


# --- Organization Update (Admin) ---
class OrganizationUpdate(BaseModel):
    name: str | None = None
    address: str | None = None
    phone: str | None = None
    license_number: str | None = None


# --- Material Price ---
class MaterialPriceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    csi_code: str
    description: str
    unit_cost: float
    unit_of_measure: str
    supplier: str | None = None
    region: str | None = None
    effective_date: str | None = None
    source: str | None = None
    created_at: datetime
    updated_at: datetime


class MaterialPriceCreate(BaseModel):
    csi_code: str
    description: str
    unit_cost: float
    unit_of_measure: str
    supplier: str | None = None
    region: str | None = None
    effective_date: str | None = None
    source: str | None = None


class MaterialPriceUpdate(BaseModel):
    csi_code: str | None = None
    description: str | None = None
    unit_cost: float | None = None
    unit_of_measure: str | None = None
    supplier: str | None = None
    region: str | None = None
    effective_date: str | None = None
    source: str | None = None


# --- Productivity Benchmark ---
class ProductivityBenchmarkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    csi_division: str
    csi_code: str | None = None
    description: str
    project_type: str | None = None
    region: str | None = None
    unit_of_measure: str
    avg_unit_cost: float
    avg_labor_cost_per_unit: float | None = None
    avg_material_cost_per_unit: float | None = None
    avg_equipment_cost_per_unit: float | None = None
    avg_sub_cost_per_unit: float | None = None
    avg_labor_hours_per_unit: float | None = None
    min_unit_cost: float | None = None
    max_unit_cost: float | None = None
    std_dev: float | None = None
    sample_size: int
    confidence_score: float | None = None
    last_computed_at: datetime
    source_project_ids: str | None = None
    organization_id: int
    created_at: datetime
    updated_at: datetime | None = None


class BenchmarkQuery(BaseModel):
    csi_division: str | None = None
    csi_code: str | None = None
    project_type: str | None = None
    region: str | None = None
    unit_of_measure: str | None = None
    min_confidence: float | None = None  # filter out low-confidence benchmarks
    min_sample_size: int | None = None


# ── Phase 1 domain spine ──────────────────────────────────────────────────────

# --- ScopePackage ---
class ScopePackageCreate(BaseModel):
    name: str
    code: str | None = None
    trade_focus: str | None = None
    csi_division: str | None = None
    status: str = "active"
    inclusions_json: str | None = None
    exclusions_json: str | None = None
    assumptions_json: str | None = None


class ScopePackageUpdate(BaseModel):
    name: str | None = None
    code: str | None = None
    trade_focus: str | None = None
    csi_division: str | None = None
    status: str | None = None
    inclusions_json: str | None = None
    exclusions_json: str | None = None
    assumptions_json: str | None = None


class ScopePackageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    name: str
    code: str | None = None
    trade_focus: str | None = None
    csi_division: str | None = None
    status: str
    inclusions_json: str | None = None
    exclusions_json: str | None = None
    assumptions_json: str | None = None
    created_at: datetime
    updated_at: datetime


# --- PlanSet ---
class PlanSetCreate(BaseModel):
    version_label: str | None = None
    upload_id: int | None = None
    source_filename: str | None = None


class PlanSetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    version_label: str | None = None
    upload_id: int | None = None
    source_filename: str | None = None
    sheet_count: int
    status: str
    created_at: datetime
    updated_at: datetime


# --- PlanSheet ---
class PlanSheetUpdate(BaseModel):
    sheet_number: str | None = None
    sheet_name: str | None = None
    discipline: str | None = None
    confirmed_scale: str | None = None
    preview_image_url: str | None = None
    width_px: int | None = None
    height_px: int | None = None
    ocr_text_json: str | None = None
    metadata_json: str | None = None


class PlanSheetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    plan_set_id: int
    sheet_number: str | None = None
    sheet_name: str | None = None
    discipline: str | None = None
    page_index: int
    preview_image_url: str | None = None
    width_px: int | None = None
    height_px: int | None = None
    detected_scale: str | None = None
    confirmed_scale: str | None = None
    created_at: datetime
    updated_at: datetime


# --- SheetRegion ---
class SheetRegionCreate(BaseModel):
    region_type: str | None = None
    bbox_json: str | None = None
    label: str | None = None
    source_method: str | None = None
    review_status: str = "pending"


class SheetRegionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    plan_sheet_id: int
    region_type: str | None = None
    bbox_json: str | None = None
    label: str | None = None
    source_method: str | None = None
    review_status: str
    created_at: datetime


# --- TakeoffLayer ---
class TakeoffLayerCreate(BaseModel):
    name: str
    trade_focus: str | None = None
    layer_type: str | None = None
    scope_package_id: int | None = None
    visibility_default: bool = True


class TakeoffLayerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    plan_sheet_id: int | None = None
    scope_package_id: int | None = None
    trade_focus: str | None = None
    name: str
    layer_type: str | None = None
    visibility_default: bool
    created_at: datetime
    updated_at: datetime


# --- PlanTakeoffItem ---
class PlanTakeoffItemCreate(BaseModel):
    item_type: str | None = None
    label: str | None = None
    measurement_type: str | None = None
    quantity: float | None = None
    unit: str | None = None
    geometry_geojson: str | None = None
    bbox_json: str | None = None
    source_method: str = "manual"
    confidence: float | None = None
    assumptions_json: str | None = None


class PlanTakeoffItemUpdate(BaseModel):
    label: str | None = None
    quantity: float | None = None
    unit: str | None = None
    geometry_geojson: str | None = None
    bbox_json: str | None = None
    review_status: str | None = None
    assumptions_json: str | None = None


class PlanTakeoffItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    plan_sheet_id: int | None = None
    takeoff_layer_id: int
    agent_run_log_id: int | None = None
    item_type: str | None = None
    label: str | None = None
    measurement_type: str | None = None
    quantity: float | None = None
    unit: str | None = None
    source_method: str
    confidence: float | None = None
    review_status: str
    created_at: datetime
    updated_at: datetime
