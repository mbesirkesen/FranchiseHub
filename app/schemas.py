import enum
from datetime import datetime
from typing import Annotated, Optional

from pydantic import (
    AliasChoices,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    computed_field,
)


def _normalize_email(v: object) -> str:
    if not isinstance(v, str):
        raise ValueError("email must be a string")
    s = v.strip().lower()
    if "@" not in s or s.count("@") != 1:
        raise ValueError("invalid email")
    local, domain = s.split("@", 1)
    if not local or not domain or "." not in domain:
        raise ValueError("invalid email")
    return s


# EmailStr .local gibi reserved TLD'leri reddeder; dev/test icin gevsetilmis tip.
LenientEmailStr = Annotated[str, BeforeValidator(_normalize_email)]


class UserRole(str, enum.Enum):
    buyer = "buyer"
    franchise_owner = "franchise_owner"


class ApplicationStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class SupplyRequestStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    shipped = "shipped"


class UserLogin(BaseModel):
    email: LenientEmailStr
    password: str


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class ForgotPasswordRequest(BaseModel):
    email: LenientEmailStr


class ForgotPasswordResponse(BaseModel):
    message: str
    reset_token: Optional[str] = None


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=10)
    new_password: str = Field(min_length=8)


class VerifyEmailRequest(BaseModel):
    email: LenientEmailStr
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(min_length=10)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


class MeUpdate(BaseModel):
    phone: Optional[str] = Field(default=None, min_length=7, max_length=30)
    first_name: Optional[str] = Field(default=None, min_length=2, max_length=100)
    last_name: Optional[str] = Field(default=None, min_length=2, max_length=100)
    city: Optional[str] = Field(default=None, min_length=2, max_length=120)
    investment_budget: Optional[float] = Field(default=None, gt=0)
    experience_years: Optional[int] = Field(default=None, ge=0)
    preferred_sector: Optional[str] = Field(default=None, min_length=2, max_length=120)
    identity_number: Optional[str] = Field(default=None, min_length=5, max_length=50)
    company_name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    authorized_person_name: Optional[str] = Field(default=None, min_length=2, max_length=180)
    country: Optional[str] = Field(default=None, min_length=2, max_length=120)
    company_address: Optional[str] = Field(default=None, min_length=5)
    website: Optional[str] = Field(default=None, max_length=255)


class MessageResponse(BaseModel):
    message: str


class BuyerBase(BaseModel):
    email: LenientEmailStr
    first_name: str = Field(min_length=2, max_length=100)
    last_name: str = Field(min_length=2, max_length=100)
    phone: str = Field(min_length=7, max_length=30)
    city: str = Field(min_length=2, max_length=120)
    investment_budget: float = Field(gt=0)
    experience_years: int = Field(ge=0)
    preferred_sector: str = Field(min_length=2, max_length=120)
    identity_number: Optional[str] = Field(default=None, min_length=5, max_length=50)


class BuyerCreate(BuyerBase):
    password: str = Field(min_length=8)


class BuyerRead(BuyerBase):
    id: int
    role: UserRole = UserRole.buyer
    is_active: bool
    email_verified: bool = False

    class Config:
        from_attributes = True


class FranchiseOwnerBase(BaseModel):
    email: LenientEmailStr
    company_name: str = Field(min_length=2, max_length=255)
    tax_number: str = Field(min_length=5, max_length=100)
    phone: str = Field(min_length=7, max_length=30)
    authorized_person_name: str = Field(min_length=2, max_length=180)
    country: str = Field(min_length=2, max_length=120)
    city: str = Field(min_length=2, max_length=120)
    company_address: str = Field(min_length=5)
    website: Optional[str] = Field(default=None, max_length=255)
    verification_status: bool = False


class FranchiseOwnerCreate(FranchiseOwnerBase):
    password: str = Field(min_length=8)


class FranchiseOwnerRead(FranchiseOwnerBase):
    id: int
    role: UserRole = UserRole.franchise_owner
    is_active: bool
    email_verified: bool = False

    class Config:
        from_attributes = True


class AuthMeResponse(BaseModel):
    role: UserRole
    email_verified: bool
    buyer: Optional[BuyerRead] = None
    franchise_owner: Optional[FranchiseOwnerRead] = None


class BrandBase(BaseModel):
    name: str
    sector: Optional[str] = None
    description: Optional[str] = None
    initial_cost: float
    support_details: Optional[str] = None
    location: Optional[str] = None


class BrandCreate(BrandBase):
    pass


class BrandRead(BrandBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_approved: bool
    franchise_owner_id: Optional[int] = None

    @computed_field
    @property
    def min_investment_cost(self) -> float:
        return self.initial_cost

    @computed_field
    @property
    def max_investment_cost(self) -> float:
        return self.initial_cost


class BrandListPage(BaseModel):
    items: list[BrandRead]
    page: int
    page_size: int
    total: int
    total_pages: int


class FranchiseOwnerBrandWrite(BaseModel):
    """Next.js: name + sector/location + min/max veya initial_cost."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    sector: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None
    support_details: Optional[str] = None
    initial_cost: Optional[float] = Field(default=None, gt=0)
    min_investment_cost: Optional[float] = Field(default=None, ge=0)
    max_investment_cost: Optional[float] = Field(default=None, ge=0)

    def resolved_initial_cost(self) -> float:
        if self.initial_cost is not None:
            return float(self.initial_cost)
        mn, mx = self.min_investment_cost, self.max_investment_cost
        if mn is not None and mx is not None:
            return (float(mn) + float(mx)) / 2.0
        if mn is not None:
            return float(mn)
        if mx is not None:
            return float(mx)
        raise ValueError(
            "Provide initial_cost or min_investment_cost / max_investment_cost"
        )


class FranchiseOwnerDashboardSummary(BaseModel):
    """Franchise sahibi paneli; Next dashboard-summary.ts ile uyumlu alan adlari."""

    has_brand: bool
    brand_id: Optional[int] = None
    brand_name: Optional[str] = None
    applications_pending: int = 0
    applications_approved: int = 0
    applications_rejected: int = 0
    applications_total: int = 0
    inventory_item_count: int = 0
    supply_requests_pending: int = 0
    supply_requests_total: int = 0

    @computed_field
    @property
    def pending_applications(self) -> int:
        return self.applications_pending

    @computed_field
    @property
    def pending(self) -> int:
        return self.applications_pending

    @computed_field
    @property
    def pending_count(self) -> int:
        return self.applications_pending

    @computed_field
    @property
    def approved_applications(self) -> int:
        return self.applications_approved

    @computed_field
    @property
    def approved(self) -> int:
        return self.applications_approved

    @computed_field
    @property
    def approved_count(self) -> int:
        return self.applications_approved

    @computed_field
    @property
    def rejected_applications(self) -> int:
        return self.applications_rejected

    @computed_field
    @property
    def rejected(self) -> int:
        return self.applications_rejected

    @computed_field
    @property
    def rejected_count(self) -> int:
        return self.applications_rejected

    @computed_field
    @property
    def total_applications(self) -> int:
        return self.applications_total

    @computed_field
    @property
    def total(self) -> int:
        return self.applications_total

    @computed_field
    @property
    def total_count(self) -> int:
        return self.applications_total

    @computed_field
    @property
    def inventory_count(self) -> int:
        return self.inventory_item_count

    @computed_field
    @property
    def inventory_items(self) -> int:
        return self.inventory_item_count

    @computed_field
    @property
    def inventory_total(self) -> int:
        return self.inventory_item_count

    @computed_field
    @property
    def supply_request_count(self) -> int:
        return self.supply_requests_total

    @computed_field
    @property
    def supply_requests(self) -> int:
        return self.supply_requests_total

    @computed_field
    @property
    def my_supply_request_count(self) -> int:
        return self.supply_requests_total

    @computed_field
    @property
    def supply_request_total(self) -> int:
        """Frontend typo alias (tekil request)."""
        return self.supply_requests_total


class ApplicationBase(BaseModel):
    buyer_id: int
    brand_id: int
    status: ApplicationStatus = ApplicationStatus.pending
    notes: Optional[str] = None


class ApplicationCreate(ApplicationBase):
    pass


class ApplicationRead(ApplicationBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: Optional[datetime] = None


class ApplicationListEnvelope(BaseModel):
    items: list[ApplicationRead]
    total: int
    page: int = 1
    page_size: int = 20
    total_pages: int = 0


class ApplicationUpdate(BaseModel):
    status: ApplicationStatus
    notes: Optional[str] = None


class BrandApprovalUpdate(BaseModel):
    is_approved: bool = True


class BrandSort(str, enum.Enum):
    name_asc = "name_asc"
    name_desc = "name_desc"
    cost_asc = "cost_asc"
    cost_desc = "cost_desc"


class BrandCompareRequest(BaseModel):
    brand_ids: list[int] = Field(min_length=2)


class BrandCompareColumn(BaseModel):
    brand_id: int
    name: str


class BrandCompareRow(BaseModel):
    key: str
    label: str
    values: list[Optional[str]]


class BrandCompareTable(BaseModel):
    columns: list[BrandCompareColumn]
    rows: list[BrandCompareRow]


class BrandCompareItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    sector: Optional[str] = None
    location: Optional[str] = None
    initial_cost: float
    support_details: Optional[str] = None
    is_approved: bool = False

    @computed_field
    @property
    def min_investment_cost(self) -> float:
        return self.initial_cost

    @computed_field
    @property
    def max_investment_cost(self) -> float:
        return self.initial_cost


class BrandFinancialSummary(BaseModel):
    """Marka başına normalize finansal özet (karşılaştırma UI)."""

    brand_id: int
    name: str
    currency: str = "TRY"
    initial_cost: float
    min_investment_cost: float
    max_investment_cost: float
    sector: Optional[str] = None
    location: Optional[str] = None
    support_details: Optional[str] = None


class BrandCompareResponse(BaseModel):
    brands: list[BrandCompareItem]
    comparison_table: BrandCompareTable
    financial_summaries: list[BrandFinancialSummary] = Field(default_factory=list)


class BrandMediaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    brand_id: int
    media_type: str
    url: str
    mime_type: str
    original_filename: Optional[str] = None
    sort_order: int = 0


class BrandMediaListResponse(BaseModel):
    logo: Optional[BrandMediaRead] = None
    gallery: list[BrandMediaRead] = Field(default_factory=list)


class BrandFDDRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    brand_id: int
    title: str
    version: Optional[str] = None
    mime_type: str
    file_size_bytes: Optional[int] = None
    published_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class BrandFDDListResponse(BaseModel):
    items: list[BrandFDDRead]


class BrandFDDUploadResponse(BaseModel):
    document: BrandFDDRead


class BrandFDDDownloadResponse(BaseModel):
    download_url: str
    expires_at: datetime
    expires_in_seconds: int


class BrandTerritoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    brand_id: int
    name: str
    region_code: Optional[str] = None
    status: str
    notes: Optional[str] = None


class BrandTerritoryListResponse(BaseModel):
    items: list[BrandTerritoryRead]
    available_count: int
    reserved_count: int


class TerritoryStatus(str, enum.Enum):
    available = "available"
    reserved = "reserved"


class BrandTerritoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    region_code: Optional[str] = Field(default=None, max_length=64)
    status: TerritoryStatus = TerritoryStatus.available
    notes: Optional[str] = None


class BrandTerritoryUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    region_code: Optional[str] = Field(default=None, max_length=64)
    status: Optional[TerritoryStatus] = None
    notes: Optional[str] = None


class RegionOption(BaseModel):
    key: str
    label: str


class RegionListResponse(BaseModel):
    items: list[RegionOption]


class MessagesReadAllResponse(BaseModel):
    application_id: int
    updated_count: int


class BrandMediaUploadResponse(BaseModel):
    media: BrandMediaRead


class OutletStatus(str, enum.Enum):
    active = "active"
    inactive = "inactive"
    planned = "planned"


class OwnerDocumentType(str, enum.Enum):
    training = "training"
    sop = "sop"
    other = "other"


class FranchiseOutletCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    city: str = Field(min_length=2, max_length=120)
    address: Optional[str] = None
    status: OutletStatus = OutletStatus.active
    opened_at: Optional[datetime] = None


class FranchiseOutletUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    city: Optional[str] = Field(default=None, min_length=2, max_length=120)
    address: Optional[str] = None
    status: Optional[OutletStatus] = None
    opened_at: Optional[datetime] = None


class FranchiseOutletRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    franchise_owner_id: int
    brand_id: Optional[int] = None
    name: str
    city: str
    address: Optional[str] = None
    status: OutletStatus
    opened_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class FranchiseOutletListResponse(BaseModel):
    items: list[FranchiseOutletRead]
    total: int
    page: int = 1
    page_size: int = 20
    total_pages: int = 0


class FranchiseOwnerDocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    franchise_owner_id: int
    title: str
    document_type: OwnerDocumentType
    mime_type: str
    file_size_bytes: Optional[int] = None
    original_filename: Optional[str] = None
    download_url: str
    created_at: Optional[datetime] = None


class FranchiseOwnerDocumentListResponse(BaseModel):
    items: list[FranchiseOwnerDocumentRead]
    total: int
    page: int = 1
    page_size: int = 20
    total_pages: int = 0


class FranchiseOwnerDocumentUploadResponse(BaseModel):
    document: FranchiseOwnerDocumentRead


class AnalyticsTimePoint(BaseModel):
    date: str
    total: int = 0
    pending: int = 0
    approved: int = 0
    rejected: int = 0


class InventoryTimePoint(BaseModel):
    date: str
    item_count: int = 0
    total_stock: int = 0
    supply_request_count: int = 0


class AnalyticsMonthPoint(BaseModel):
    month: str
    total: int = 0
    pending: int = 0
    approved: int = 0
    rejected: int = 0


class SupplyRequestsByStatus(BaseModel):
    pending: int = 0
    approved: int = 0
    rejected: int = 0
    shipped: int = 0


class FranchiseOwnerAnalyticsResponse(BaseModel):
    period_days: int
    applications: list[AnalyticsTimePoint]
    inventory: list[InventoryTimePoint]
    applications_total_in_period: int = 0
    supply_requests_total: int = 0
    supply_requests_total_in_period: int = 0
    inventory_current: dict[str, int] = Field(default_factory=dict)
    applications_by_month: list[AnalyticsMonthPoint] = Field(default_factory=list)
    inventory_total_quantity: int = 0
    supply_requests_by_status: SupplyRequestsByStatus = Field(
        default_factory=SupplyRequestsByStatus
    )

    @computed_field
    @property
    def application_series(self) -> list[AnalyticsTimePoint]:
        return self.applications

    @computed_field
    @property
    def inventory_series(self) -> list[InventoryTimePoint]:
        return self.inventory

    @computed_field
    @property
    def supply_request_count(self) -> int:
        return self.supply_requests_total

    @computed_field
    @property
    def supply_requests(self) -> int:
        return self.supply_requests_total


class BuyerApplicationCreate(BaseModel):
    brand_id: int
    notes: Optional[str] = None


class BuyerFavoritesResponse(BaseModel):
    items: list[int]
    total: int
    page: int = 1
    page_size: int = 20
    total_pages: int = 0

    @computed_field
    @property
    def brand_ids(self) -> list[int]:
        return self.items


class BuyerApplicationBrandSummary(BaseModel):
    id: int
    name: str
    sector: Optional[str] = None
    location: Optional[str] = None
    initial_cost: float


class BuyerApplicationListItem(BaseModel):
    id: int
    brand_id: int
    status: ApplicationStatus
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    brand: BuyerApplicationBrandSummary


class BuyerApplicationsListResponse(BaseModel):
    items: list[BuyerApplicationListItem]
    total: int
    page: int = 1
    page_size: int = 20
    total_pages: int = 0


class BuyerApplicationDetailResponse(BaseModel):
    id: int
    buyer_id: int
    brand_id: int
    status: ApplicationStatus
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    brand: BrandRead


class BuyerDashboardSummary(BaseModel):
    favorites_count: int = 0
    applications_pending: int = 0
    applications_approved: int = 0
    applications_rejected: int = 0
    applications_total: int = 0

    @computed_field
    @property
    def pending_applications(self) -> int:
        return self.applications_pending

    @computed_field
    @property
    def pending_count(self) -> int:
        return self.applications_pending


class BuyerQualificationRequest(BaseModel):
    investment_budget: float = Field(gt=0)
    preferred_sector: str = Field(min_length=2, max_length=120)
    experience_years: int = Field(ge=0)
    city: Optional[str] = Field(default=None, min_length=2, max_length=120)


class RecommendedBrandItem(BaseModel):
    brand: BrandRead
    match_score: int = Field(ge=0, le=100)
    match_reasons: list[str] = Field(default_factory=list)


class BuyerQualificationResponse(BaseModel):
    items: list[RecommendedBrandItem]
    matching_engine: str = "rules"


class MessageCreate(BaseModel):
    application_id: int
    content: str


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: int
    sender_role: UserRole
    sender_id: int
    content: str
    created_at: Optional[datetime] = None
    is_read: bool = False
    read_at: Optional[datetime] = None

    @computed_field
    @property
    def is_from_buyer(self) -> bool:
        return self.sender_role == UserRole.buyer


class MessageReadUpdateResponse(BaseModel):
    id: int
    is_read: bool
    read_at: datetime


class ConversationLastMessage(BaseModel):
    id: int
    content: str
    sender_role: UserRole
    created_at: Optional[datetime] = None


class ConversationItem(BaseModel):
    application_id: int
    application_status: ApplicationStatus
    brand_id: int
    brand_name: str
    buyer_id: int
    buyer_name: str
    unread_count: int = 0
    last_message: Optional[ConversationLastMessage] = None


class ConversationsResponse(BaseModel):
    items: list[ConversationItem]


class ApplicationParticipantBuyer(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    first_name: str
    last_name: str
    email: LenientEmailStr
    phone: str
    city: str
    investment_budget: float
    experience_years: int
    preferred_sector: str


class ApplicationExtendedStatus(str, enum.Enum):
    submitted = "submitted"
    under_review = "under_review"
    approved = "approved"
    rejected = "rejected"
    in_conversation = "in_conversation"


class ApplicationDetailResponse(BaseModel):
    id: int
    buyer_id: int
    brand_id: int
    status: ApplicationStatus
    extended_status: Optional[ApplicationExtendedStatus] = None
    extended_status_label: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    brand: BrandRead
    buyer: Optional[ApplicationParticipantBuyer] = None
    message_count: int = 0
    unread_count: int = 0


class ApplicationMineListItem(BaseModel):
    id: int
    brand_id: int
    status: ApplicationStatus
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    brand: BuyerApplicationBrandSummary
    unread_count: int = 0


class ApplicationsMineResponse(BaseModel):
    items: list[ApplicationMineListItem]
    total: int
    page: int = 1
    page_size: int = 20
    total_pages: int = 0


class SupplyRequestBase(BaseModel):
    franchise_owner_id: int
    product_name: str
    quantity: int
    status: SupplyRequestStatus = SupplyRequestStatus.pending


class SupplyRequestCreate(SupplyRequestBase):
    pass


class SupplyRequestRead(SupplyRequestBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class SupplyRequestDetailRead(SupplyRequestRead):
    pass


class SupplyRequestUpdate(BaseModel):
    status: SupplyRequestStatus
    notes: Optional[str] = None


class SupplyRequestListEnvelope(BaseModel):
    items: list[SupplyRequestRead]
    total: int
    page: int = 1
    page_size: int = 20
    total_pages: int = 0


class SupplyRequestItemCreate(BaseModel):
    product_name: str
    quantity: int = Field(gt=0)


class SupplyRequestBulkCreate(BaseModel):
    requests: list[SupplyRequestItemCreate] = Field(min_length=1)


class SupplyPoolItem(BaseModel):
    product_name: str
    total_quantity: int
    request_count: int
    franchise_owner_count: int


class InventoryBase(BaseModel):
    franchise_owner_id: int
    item_name: str
    stock_level: int


class InventoryCreate(InventoryBase):
    pass


class InventoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    franchise_owner_id: int
    outlet_id: Optional[int] = None
    item_name: str
    stock_level: int
    low_stock_threshold: int = 10

    @computed_field
    @property
    def product_name(self) -> str:
        return self.item_name

    @computed_field
    @property
    def quantity(self) -> int:
        return self.stock_level

    @computed_field
    @property
    def is_low_stock(self) -> bool:
        return self.stock_level < self.low_stock_threshold


class InventoryListEnvelope(BaseModel):
    items: list[InventoryRead]
    total: int
    page: int = 1
    page_size: int = 20
    total_pages: int = 0


class InventoryItemCreate(BaseModel):
    item_name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        validation_alias=AliasChoices("item_name", "product_name"),
    )
    stock_level: int = Field(
        ...,
        ge=0,
        validation_alias=AliasChoices("stock_level", "quantity"),
    )
    outlet_id: Optional[int] = None
    low_stock_threshold: int = Field(default=10, ge=0)


class InventoryItemUpdate(BaseModel):
    item_name: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=255,
        validation_alias=AliasChoices("item_name", "product_name"),
    )
    stock_level: Optional[int] = Field(
        default=None,
        ge=0,
        validation_alias=AliasChoices("stock_level", "quantity"),
    )
    outlet_id: Optional[int] = None
    low_stock_threshold: Optional[int] = Field(default=None, ge=0)


class InventoryTransferRequest(BaseModel):
    inventory_id: int
    from_outlet_id: Optional[int] = None
    to_outlet_id: Optional[int] = None
    quantity: int = Field(gt=0)


class InventoryTransferRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    franchise_owner_id: int
    from_outlet_id: Optional[int] = None
    to_outlet_id: Optional[int] = None
    inventory_id: int
    item_name: str
    quantity: int
    created_at: Optional[datetime] = None
    source_stock_after: int
    destination_stock_after: int


class LowStockInventoryItem(InventoryRead):
    deficit: int


class LowStockListResponse(BaseModel):
    items: list[LowStockInventoryItem]
    total: int
    page: int = 1
    page_size: int = 20
    total_pages: int = 0
    threshold_default: int = 10


class AuthenticatedPrincipal(BaseModel):
    role: UserRole
    user_id: int
    email: LenientEmailStr


class DevicePlatform(str, enum.Enum):
    ios = "ios"
    android = "android"
    web = "web"


class NotificationRead(BaseModel):
    id: int
    title: str
    body: str
    notification_type: str = "general"
    action_url: Optional[str] = None
    resource_type: Optional[str] = None
    resource_id: Optional[int] = None
    is_read: bool
    read_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    @computed_field
    @property
    def type(self) -> str:
        return self.notification_type

    @computed_field
    @property
    def message(self) -> str:
        return self.body

    @computed_field
    @property
    def link(self) -> Optional[str]:
        return self.action_url

    @computed_field
    @property
    def target_type(self) -> Optional[str]:
        return self.resource_type

    @computed_field
    @property
    def target_id(self) -> Optional[int]:
        return self.resource_id

    @computed_field
    @property
    def read(self) -> bool:
        return self.is_read


class NotificationListResponse(BaseModel):
    items: list[NotificationRead]
    page: int
    page_size: int
    total: int
    total_pages: int
    unread_count: int


class NotificationReadResponse(BaseModel):
    id: int
    is_read: bool
    read_at: datetime


class NotificationReadAllResponse(BaseModel):
    updated_count: int


class DeviceRegisterRequest(BaseModel):
    token: str = Field(min_length=10, max_length=512)
    platform: DevicePlatform


class PushDeviceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    token: str
    platform: DevicePlatform
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class DeviceRegisterResponse(BaseModel):
    device: PushDeviceRead
    message: str = "Device registered"


class FileUploadResponse(BaseModel):
    file_id: int
    url: str
    mime_type: str
    original_filename: Optional[str] = None
    file_size_bytes: Optional[int] = None


class SearchBrandHit(BaseModel):
    id: int
    name: str
    sector: Optional[str] = None
    location: Optional[str] = None
    is_approved: bool


class SearchApplicationHit(BaseModel):
    id: int
    status: ApplicationStatus
    buyer_email: Optional[str] = None
    buyer_name: Optional[str] = None
    brand_name: Optional[str] = None
    notes: Optional[str] = None


class SearchResponse(BaseModel):
    query: str
    brands: list[SearchBrandHit] = Field(default_factory=list)
    applications: list[SearchApplicationHit] = Field(default_factory=list)


class AssistantQueryRequest(BaseModel):
    query: str = Field(min_length=2, max_length=2000)
    brand_id: Optional[int] = None


class AssistantSuggestion(BaseModel):
    label: str
    action: str
    brand_id: Optional[int] = None
    match_score: Optional[int] = None


class AssistantQueryResponse(BaseModel):
    answer: str
    intent: str = "general"
    suggestions: list[AssistantSuggestion] = Field(default_factory=list)
    related_brands: list[BrandRead] = Field(default_factory=list)
    related_brand_ids: list[int] = Field(default_factory=list)
    filters_applied: dict[str, object] = Field(default_factory=dict)
    source: str = "rules"

    @computed_field
    @property
    def reply(self) -> str:
        return self.answer

    @computed_field
    @property
    def brands(self) -> list[BrandRead]:
        return self.related_brands


class TimelineStepStatus(str, enum.Enum):
    done = "done"
    active = "active"
    pending = "pending"
    failed = "failed"


class ApplicationTimelineStep(BaseModel):
    id: str
    label: str
    status: TimelineStepStatus
    at: Optional[datetime] = None


class ApplicationTimelineEvent(BaseModel):
    id: str
    event_type: str
    title: str
    description: Optional[str] = None
    occurred_at: Optional[datetime] = None
    actor_role: Optional[UserRole] = None
    status: Optional[ApplicationStatus] = None
    extended_status: Optional[ApplicationExtendedStatus] = None


class ApplicationTimelineResponse(BaseModel):
    application_id: int
    status: ApplicationStatus
    extended_status: ApplicationExtendedStatus
    extended_status_label: str
    steps: list[ApplicationTimelineStep] = Field(default_factory=list)
    events: list[ApplicationTimelineEvent] = Field(default_factory=list)


class BrandGrowthPoint(BaseModel):
    month: str
    value: float


class BrandMetricsResponse(BaseModel):
    brand_id: int
    brand_name: str
    applications_total: int = 0
    applications_approved: int = 0
    applications_pending: int = 0
    territories_available: int = 0
    territories_reserved: int = 0
    territories_total: int = 0
    outlet_count: int = 0
    fdd_document_count: int = 0
    media_gallery_count: int = 0
    has_logo: bool = False
    initial_cost: float
    sector: Optional[str] = None
    location: Optional[str] = None
    estimated_roi_percent: float = 0.0
    growth_series: list[BrandGrowthPoint] = Field(default_factory=list)


class EcosystemNode(BaseModel):
    id: str
    type: str
    label: str
    meta: dict[str, object] = Field(default_factory=dict)


class EcosystemEdge(BaseModel):
    id: str
    source: str
    target: str
    type: str = "link"


class GeographyDemandPoint(BaseModel):
    city: str
    region: Optional[str] = None
    application_count: int = 0
    intensity: float = 0.0


class FranchiseOwnerGeographyResponse(BaseModel):
    period_days: int = 30
    points: list[GeographyDemandPoint] = Field(default_factory=list)


class FranchiseOwnerEcosystemResponse(BaseModel):
    has_brand: bool
    brand: Optional[BrandRead] = None
    outlets_total: int = 0
    outlets_active: int = 0
    documents_total: int = 0
    applications_pending: int = 0
    applications_approved: int = 0
    applications_rejected: int = 0
    applications_total: int = 0
    inventory_item_count: int = 0
    inventory_total_stock: int = 0
    supply_requests_pending: int = 0
    supply_requests_total: int = 0
    nodes: list[EcosystemNode] = Field(default_factory=list)
    edges: list[EcosystemEdge] = Field(default_factory=list)

