"""Pydantic v2 schemas for API request/response validation."""

from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


# --- Base ---
class APIResponse(BaseModel):
    success: bool = True
    message: str = ""
    data: Optional[dict | list] = None
    error: Optional[str] = None


# --- Chunked Upload ---
class ChunkedUploadInitRequest(BaseModel):
    filename: str
    file_size: int
    content_type: str = "application/octet-stream"


# --- Organization ---
class OrganizationCreate(BaseModel):
    name: str
    address: Optional[str] = None
    phone: Optional[str] = None
    license_number: Optional[str] = None


class OrganizationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    address: Optional[str] = None
    phone: Optional[str] = None
    license_number: Optional[str] = None
    created_at: datetime


# --- User ---
class UserCreate(BaseModel):
    email: str
    password: str
    full_name: str
    role: str = "estimator"
    organization_id: Optional[int] = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    full_name: str
    role: str
    organization_id: Optional[int] = None


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: Optional["UserOut"] = None


# --- Project ---
class ProjectCreate(BaseModel):
    name: str
    project_number: Optional[str] = None
    project_type: str = "commercial"
    description: Optional[str] = None
    location: Optional[str] = None
    square_footage: Optional[float] = None
    estimated_value: Optional[float] = None
    bid_date: Optional[str] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    project_type: Optional[str] = None
    status: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    square_footage: Optional[float] = None
    estimated_value: Optional[float] = None
    bid_date: Optional[str] = None


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    project_number: str
    project_type: str
    status: str
    description: Optional[str] = None
    location: Optional[str] = None
    square_footage: Optional[float] = None
    estimated_value: Optional[float] = None
    bid_date: Optional[str] = None
    created_at: datetime
    updated_at: datetime


# --- Document ---
class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    filename: str
    file_type: str
    classification: Optional[str] = None
    file_size_bytes: Optional[int] = None
    page_count: Optional[int] = None
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
    work_description: Optional[str] = None
    materials_referenced: Optional[list] = None
    execution_requirements: Optional[str] = None
    submittal_requirements: Optional[str] = None
    keywords: Optional[list] = None


# --- Gap Report ---
class GapReportItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    division_number: str
    section_number: Optional[str] = None
    title: str
    gap_type: str
    severity: str
    description: Optional[str] = None
    recommendation: Optional[str] = None
    risk_score: Optional[float] = None


class GapReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    overall_score: Optional[float] = None
    total_gaps: int
    critical_count: int
    moderate_count: int
    watch_count: int
    summary: Optional[str] = None
    items: list[GapReportItemOut] = []
    created_at: datetime


# --- Takeoff ---
class TakeoffItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    spec_section_id: Optional[int] = None
    csi_code: str
    description: str
    quantity: float
    unit_of_measure: str
    drawing_reference: Optional[str] = None
    confidence: float
    notes: Optional[str] = None
    is_manual_override: int


class TakeoffItemUpdate(BaseModel):
    description: Optional[str] = None
    quantity: Optional[float] = None
    unit_of_measure: Optional[str] = None
    notes: Optional[str] = None


# --- Labor Estimate ---
class LaborEstimateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    takeoff_item_id: int
    csi_code: str
    work_type: Optional[str] = None
    crew_type: Optional[str] = None
    productivity_rate: float
    quantity: float
    labor_hours: float
    crew_size: int
    crew_days: Optional[float] = None
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
    exclusions: Optional[list] = None
    assumptions: Optional[list] = None
    alternates: Optional[list] = None
    bid_bond_required: int
    line_items: list[EstimateLineItemOut] = []
    created_at: datetime


# --- Actuals & Variance ---
class ProjectActualOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    csi_code: str
    description: Optional[str] = None
    estimated_quantity: Optional[float] = None
    actual_quantity: Optional[float] = None
    estimated_labor_hours: Optional[float] = None
    actual_labor_hours: Optional[float] = None
    estimated_cost: Optional[float] = None
    actual_cost: Optional[float] = None
    variance_hours: Optional[float] = None
    variance_cost: Optional[float] = None
    variance_pct: Optional[float] = None


class VarianceReportOut(BaseModel):
    project_id: int
    total_items: int
    overall_variance_pct: Optional[float] = None
    accuracy_score: Optional[float] = None
    items: list[ProjectActualOut] = []
    by_division: Optional[dict] = None


# --- Productivity ---
class ProductivityHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    csi_code: str
    work_type: str
    crew_type: Optional[str] = None
    productivity_rate: float
    unit_of_measure: str
    source_project: Optional[str] = None
    is_actual: int
    confidence_score: float
    sample_count: int


class ProductivityUpdate(BaseModel):
    productivity_rate: Optional[float] = None
    crew_type: Optional[str] = None
    notes: Optional[str] = None


# --- Equipment Rate ---
class EquipmentRateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    division_number: str
    csi_code: Optional[str] = None
    equipment_pct: float
    description: Optional[str] = None
    region: Optional[str] = None
    created_at: datetime
    updated_at: datetime

class EquipmentRateCreate(BaseModel):
    division_number: str
    csi_code: Optional[str] = None
    equipment_pct: float
    description: Optional[str] = None
    region: Optional[str] = None

class EquipmentRateUpdate(BaseModel):
    division_number: Optional[str] = None
    csi_code: Optional[str] = None
    equipment_pct: Optional[float] = None
    description: Optional[str] = None
    region: Optional[str] = None


# --- Estimate Markup ---
class EstimateMarkupUpdate(BaseModel):
    overhead_pct: Optional[float] = None
    profit_pct: Optional[float] = None
    contingency_pct: Optional[float] = None
    gc_markup_pct: Optional[float] = None


# --- Pipeline Status ---
class AgentStepStatus(BaseModel):
    agent_number: int
    agent_name: str
    status: str  # pending / running / completed / failed / skipped
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_seconds: Optional[float] = None
    error_message: Optional[str] = None
    output_summary: Optional[str] = None


class PipelineStatusOut(BaseModel):
    project_id: int
    agents: list[AgentStepStatus]
    overall: str  # pending / running / completed / failed


# --- Bid Comparison ---
class BidComparisonItemCreate(BaseModel):
    division_number: str
    csi_code: Optional[str] = None
    description: Optional[str] = None
    amount: float = 0.0
    unit_cost: Optional[float] = None
    quantity: Optional[float] = None
    unit_of_measure: Optional[str] = None
    notes: Optional[str] = None


class BidComparisonItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    comparison_id: int
    division_number: str
    csi_code: Optional[str] = None
    description: Optional[str] = None
    amount: float
    unit_cost: Optional[float] = None
    quantity: Optional[float] = None
    unit_of_measure: Optional[str] = None
    notes: Optional[str] = None


class BidComparisonCreate(BaseModel):
    name: str
    source_type: str = "competitor"
    bid_date: Optional[str] = None
    total_bid_amount: Optional[float] = None
    notes: Optional[str] = None
    items: list[BidComparisonItemCreate] = []


class BidComparisonOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    name: str
    source_type: str
    bid_date: Optional[str] = None
    total_bid_amount: Optional[float] = None
    notes: Optional[str] = None
    items: list[BidComparisonItemOut] = []
    created_at: datetime


# --- Change Order ---
class ChangeOrderCreate(BaseModel):
    title: str
    description: Optional[str] = None
    csi_code: Optional[str] = None
    change_type: str = "addition"
    requested_by: Optional[str] = None
    cost_impact: float = 0.0
    schedule_impact_days: int = 0
    status: str = "pending"


class ChangeOrderUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    csi_code: Optional[str] = None
    change_type: Optional[str] = None
    requested_by: Optional[str] = None
    cost_impact: Optional[float] = None
    schedule_impact_days: Optional[int] = None
    status: Optional[str] = None


class ChangeOrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    co_number: str
    title: str
    description: Optional[str] = None
    csi_code: Optional[str] = None
    change_type: str
    requested_by: Optional[str] = None
    cost_impact: float
    schedule_impact_days: int
    status: str
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
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
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    tokens_used: Optional[int] = None
    output_summary: Optional[str] = None
    error_message: Optional[str] = None


# --- User Update (Admin) ---
class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None


# --- Organization Update (Admin) ---
class OrganizationUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    license_number: Optional[str] = None


# --- Material Price ---
class MaterialPriceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    csi_code: str
    description: str
    unit_cost: float
    unit_of_measure: str
    supplier: Optional[str] = None
    region: Optional[str] = None
    effective_date: Optional[str] = None
    source: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class MaterialPriceCreate(BaseModel):
    csi_code: str
    description: str
    unit_cost: float
    unit_of_measure: str
    supplier: Optional[str] = None
    region: Optional[str] = None
    effective_date: Optional[str] = None
    source: Optional[str] = None


class MaterialPriceUpdate(BaseModel):
    csi_code: Optional[str] = None
    description: Optional[str] = None
    unit_cost: Optional[float] = None
    unit_of_measure: Optional[str] = None
    supplier: Optional[str] = None
    region: Optional[str] = None
    effective_date: Optional[str] = None
    source: Optional[str] = None
