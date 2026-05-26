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
    admin = "admin"


class ApplicationStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class SupplyRequestStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class UserLogin(BaseModel):
    email: LenientEmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


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

    class Config:
        from_attributes = True


class AdminBase(BaseModel):
    email: LenientEmailStr
    full_name: str = Field(min_length=2, max_length=180)
    phone: str = Field(min_length=7, max_length=30)
    authorization_level: str = Field(min_length=3, max_length=50, default="standard")
    is_superadmin: bool = False


class AdminCreate(AdminBase):
    password: str = Field(min_length=8)


class AdminRead(AdminBase):
    id: int
    role: UserRole = UserRole.admin
    is_active: bool

    class Config:
        from_attributes = True


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


class ApplicationUpdate(BaseModel):
    status: ApplicationStatus
    notes: Optional[str] = None


class BrandApprovalUpdate(BaseModel):
    is_approved: bool = True


class BrandCompareRequest(BaseModel):
    brand_ids: list[int] = Field(min_length=2)


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


class BrandCompareResponse(BaseModel):
    brands: list[BrandCompareItem]


class BuyerApplicationCreate(BaseModel):
    brand_id: int
    notes: Optional[str] = None


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

    @computed_field
    @property
    def is_from_buyer(self) -> bool:
        return self.sender_role == UserRole.buyer


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


class SupplyRequestListEnvelope(BaseModel):
    items: list[SupplyRequestRead]


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
    item_name: str
    stock_level: int

    @computed_field
    @property
    def product_name(self) -> str:
        return self.item_name

    @computed_field
    @property
    def quantity(self) -> int:
        return self.stock_level


class InventoryListEnvelope(BaseModel):
    items: list[InventoryRead]


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


class AuthenticatedPrincipal(BaseModel):
    role: UserRole
    user_id: int
    email: LenientEmailStr
