import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .database import Base


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


class AuthTokenType(str, enum.Enum):
    password_reset = "password_reset"
    email_verify = "email_verify"
    refresh = "refresh"


class BrandMediaType(str, enum.Enum):
    logo = "logo"
    gallery = "gallery"


class TerritoryStatus(str, enum.Enum):
    available = "available"
    reserved = "reserved"


class OutletStatus(str, enum.Enum):
    active = "active"
    inactive = "inactive"
    planned = "planned"


class OwnerDocumentType(str, enum.Enum):
    training = "training"
    sop = "sop"
    other = "other"


class DevicePlatform(str, enum.Enum):
    ios = "ios"
    android = "android"
    web = "web"


class UserCredentialsMixin:
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    email_verified = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class Buyer(Base, UserCredentialsMixin):
    __tablename__ = "buyers"

    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    phone = Column(String(30), nullable=False)
    city = Column(String(120), nullable=False)
    investment_budget = Column(Float, nullable=False)
    experience_years = Column(Integer, nullable=False, default=0)
    preferred_sector = Column(String(120), nullable=False)
    identity_number = Column(String(50), unique=True, nullable=True)

    applications = relationship("Application", back_populates="buyer")
    favorites = relationship("BuyerFavorite", back_populates="buyer", cascade="all, delete-orphan")
    agent_sessions = relationship(
        "AgentSession", back_populates="buyer", cascade="all, delete-orphan"
    )


class BuyerFavorite(Base):
    __tablename__ = "buyer_favorites"
    __table_args__ = (UniqueConstraint("buyer_id", "brand_id", name="uq_buyer_favorites_buyer_brand"),)

    id = Column(Integer, primary_key=True, index=True)
    buyer_id = Column(Integer, ForeignKey("buyers.id"), nullable=False, index=True)
    brand_id = Column(Integer, ForeignKey("brands.id"), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    buyer = relationship("Buyer", back_populates="favorites")
    brand = relationship("Brand")


class FranchiseOwner(Base, UserCredentialsMixin):
    __tablename__ = "franchise_owners"

    id = Column(Integer, primary_key=True, index=True)
    company_name = Column(String(255), nullable=False)
    tax_number = Column(String(100), unique=True, nullable=False, index=True)
    phone = Column(String(30), nullable=False)
    authorized_person_name = Column(String(180), nullable=False)
    country = Column(String(120), nullable=False)
    city = Column(String(120), nullable=False)
    company_address = Column(Text, nullable=False)
    website = Column(String(255), nullable=True)
    verification_status = Column(Boolean, nullable=False, default=False)

    brands = relationship("Brand", back_populates="franchise_owner")
    supply_requests = relationship("SupplyRequest", back_populates="franchise_owner")
    inventories = relationship("Inventory", back_populates="franchise_owner")
    outlets = relationship("FranchiseOutlet", back_populates="franchise_owner", cascade="all, delete-orphan")
    documents = relationship(
        "FranchiseOwnerDocument",
        back_populates="franchise_owner",
        cascade="all, delete-orphan",
    )


class Brand(Base):
    __tablename__ = "brands"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    franchise_owner_id = Column(
        Integer, ForeignKey("franchise_owners.id"), nullable=True, index=True
    )
    sector = Column(String(255), nullable=True, index=True)
    description = Column(Text, nullable=True)
    initial_cost = Column(Float, nullable=False)
    support_details = Column(Text, nullable=True)
    location = Column(String(255), nullable=True)
    is_approved = Column(Boolean, nullable=False, default=False)

    franchise_owner = relationship("FranchiseOwner", back_populates="brands")
    applications = relationship("Application", back_populates="brand")
    media = relationship("BrandMedia", back_populates="brand", cascade="all, delete-orphan")
    fdd_documents = relationship(
        "BrandFDDDocument", back_populates="brand", cascade="all, delete-orphan"
    )
    territories = relationship(
        "BrandTerritory", back_populates="brand", cascade="all, delete-orphan"
    )


class BrandMedia(Base):
    __tablename__ = "brand_media"

    id = Column(Integer, primary_key=True, index=True)
    brand_id = Column(Integer, ForeignKey("brands.id"), nullable=False, index=True)
    media_type = Column(Enum(BrandMediaType, name="brand_media_type"), nullable=False)
    file_path = Column(String(512), nullable=False)
    mime_type = Column(String(128), nullable=False)
    original_filename = Column(String(255), nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    brand = relationship("Brand", back_populates="media")


class BrandFDDDocument(Base):
    __tablename__ = "brand_fdd_documents"

    id = Column(Integer, primary_key=True, index=True)
    brand_id = Column(Integer, ForeignKey("brands.id"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    version = Column(String(64), nullable=True)
    file_path = Column(String(512), nullable=False)
    mime_type = Column(String(128), nullable=False, default="application/pdf")
    file_size_bytes = Column(Integer, nullable=True)
    published_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    brand = relationship("Brand", back_populates="fdd_documents")


class BrandTerritory(Base):
    __tablename__ = "brand_territories"

    id = Column(Integer, primary_key=True, index=True)
    brand_id = Column(Integer, ForeignKey("brands.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    region_code = Column(String(64), nullable=True)
    status = Column(
        Enum(TerritoryStatus, name="territory_status"),
        nullable=False,
        default=TerritoryStatus.available,
    )
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    brand = relationship("Brand", back_populates="territories")


class Application(Base):
    __tablename__ = "applications"

    id = Column(Integer, primary_key=True, index=True)
    buyer_id = Column(Integer, ForeignKey("buyers.id"), nullable=False)
    brand_id = Column(Integer, ForeignKey("brands.id"), nullable=False)
    status = Column(
        Enum(ApplicationStatus, name="application_status"),
        nullable=False,
        default=ApplicationStatus.pending,
    )
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    buyer = relationship("Buyer", back_populates="applications")
    brand = relationship("Brand", back_populates="applications")
    messages = relationship("Message", back_populates="application")


class FranchiseOutlet(Base):
    __tablename__ = "franchise_outlets"

    id = Column(Integer, primary_key=True, index=True)
    franchise_owner_id = Column(
        Integer, ForeignKey("franchise_owners.id"), nullable=False, index=True
    )
    brand_id = Column(Integer, ForeignKey("brands.id"), nullable=True, index=True)
    name = Column(String(255), nullable=False)
    city = Column(String(120), nullable=False)
    address = Column(Text, nullable=True)
    status = Column(
        Enum(OutletStatus, name="outlet_status"),
        nullable=False,
        default=OutletStatus.active,
    )
    opened_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    franchise_owner = relationship("FranchiseOwner", back_populates="outlets")


class FranchiseOwnerDocument(Base):
    __tablename__ = "franchise_owner_documents"

    id = Column(Integer, primary_key=True, index=True)
    franchise_owner_id = Column(
        Integer, ForeignKey("franchise_owners.id"), nullable=False, index=True
    )
    title = Column(String(255), nullable=False)
    document_type = Column(
        Enum(OwnerDocumentType, name="owner_document_type"),
        nullable=False,
        default=OwnerDocumentType.other,
    )
    file_path = Column(String(512), nullable=False)
    mime_type = Column(String(128), nullable=False)
    file_size_bytes = Column(Integer, nullable=True)
    original_filename = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    franchise_owner = relationship("FranchiseOwner", back_populates="documents")


class SupplyRequest(Base):
    __tablename__ = "supply_requests"

    id = Column(Integer, primary_key=True, index=True)
    franchise_owner_id = Column(Integer, ForeignKey("franchise_owners.id"), nullable=False)
    product_name = Column(String(255), nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(
        Enum(SupplyRequestStatus, name="supply_request_status"),
        nullable=False,
        default=SupplyRequestStatus.pending,
    )
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    franchise_owner = relationship("FranchiseOwner", back_populates="supply_requests")


class Inventory(Base):
    __tablename__ = "inventories"

    id = Column(Integer, primary_key=True, index=True)
    franchise_owner_id = Column(Integer, ForeignKey("franchise_owners.id"), nullable=False)
    outlet_id = Column(Integer, ForeignKey("franchise_outlets.id"), nullable=True, index=True)
    item_name = Column(String(255), nullable=False)
    stock_level = Column(Integer, nullable=False, default=0)
    low_stock_threshold = Column(Integer, nullable=False, default=10)

    franchise_owner = relationship("FranchiseOwner", back_populates="inventories")


class InventoryTransfer(Base):
    __tablename__ = "inventory_transfers"

    id = Column(Integer, primary_key=True, index=True)
    franchise_owner_id = Column(
        Integer, ForeignKey("franchise_owners.id"), nullable=False, index=True
    )
    from_outlet_id = Column(Integer, ForeignKey("franchise_outlets.id"), nullable=True)
    to_outlet_id = Column(Integer, ForeignKey("franchise_outlets.id"), nullable=True)
    inventory_id = Column(Integer, ForeignKey("inventories.id"), nullable=False)
    item_name = Column(String(255), nullable=False)
    quantity = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    recipient_role = Column(Enum(UserRole, name="user_role"), nullable=False, index=True)
    recipient_id = Column(Integer, nullable=False, index=True)
    title = Column(String(255), nullable=False)
    body = Column(Text, nullable=False)
    notification_type = Column(String(64), nullable=False, default="general")
    action_url = Column(String(512), nullable=True)
    resource_type = Column(String(64), nullable=True)
    resource_id = Column(Integer, nullable=True)
    is_read = Column(Boolean, nullable=False, default=False, index=True)
    read_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class UploadedFile(Base):
    __tablename__ = "uploaded_files"

    id = Column(Integer, primary_key=True, index=True)
    uploader_role = Column(Enum(UserRole, name="user_role"), nullable=False, index=True)
    uploader_id = Column(Integer, nullable=False, index=True)
    file_path = Column(String(512), nullable=False)
    mime_type = Column(String(128), nullable=False)
    original_filename = Column(String(255), nullable=True)
    file_size_bytes = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class PushDevice(Base):
    __tablename__ = "push_devices"
    __table_args__ = (
        UniqueConstraint(
            "recipient_role", "recipient_id", "token", name="uq_push_devices_recipient_token"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    recipient_role = Column(Enum(UserRole, name="user_role"), nullable=False, index=True)
    recipient_id = Column(Integer, nullable=False, index=True)
    token = Column(String(512), nullable=False, index=True)
    platform = Column(Enum(DevicePlatform, name="device_platform"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class AuthToken(Base):
    __tablename__ = "auth_tokens"

    id = Column(Integer, primary_key=True, index=True)
    token_type = Column(Enum(AuthTokenType, name="auth_token_type"), nullable=False, index=True)
    token_hash = Column(String(64), nullable=False, index=True)
    role = Column(Enum(UserRole, name="user_role"), nullable=False)
    subject_id = Column(Integer, nullable=False, index=True)
    email = Column(String(255), nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    application_id = Column(Integer, ForeignKey("applications.id"), nullable=False, index=True)
    sender_role = Column(Enum(UserRole, name="message_sender_role"), nullable=False)
    sender_id = Column(Integer, nullable=False, index=True)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    application = relationship("Application", back_populates="messages")
    read_receipts = relationship(
        "MessageReadReceipt", back_populates="message", cascade="all, delete-orphan"
    )


class MessageReadReceipt(Base):
    __tablename__ = "message_read_receipts"
    __table_args__ = (
        UniqueConstraint(
            "message_id", "reader_role", "reader_id", name="uq_message_read_receipts"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("messages.id"), nullable=False, index=True)
    reader_role = Column(Enum(UserRole, name="user_role"), nullable=False)
    reader_id = Column(Integer, nullable=False, index=True)
    read_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    message = relationship("Message", back_populates="read_receipts")


class AgentMessageRole(str, enum.Enum):
    user = "user"
    assistant = "assistant"


class AgentSession(Base):
    __tablename__ = "agent_sessions"

    id = Column(Integer, primary_key=True, index=True)
    buyer_id = Column(Integer, ForeignKey("buyers.id"), nullable=False, index=True)
    title = Column(String(200), nullable=True)
    brand_context_id = Column(Integer, ForeignKey("brands.id"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    buyer = relationship("Buyer", back_populates="agent_sessions")
    messages = relationship(
        "AgentMessage", back_populates="session", cascade="all, delete-orphan", order_by="AgentMessage.created_at"
    )


class AgentMessage(Base):
    __tablename__ = "agent_messages"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("agent_sessions.id"), nullable=False, index=True)
    role = Column(String(16), nullable=False)
    content = Column(Text, nullable=False)
    intent = Column(String(64), nullable=True)
    source = Column(String(16), nullable=False, default="rules")
    filters_applied = Column(JSON, nullable=True)
    related_brand_ids = Column(JSON, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    session = relationship("AgentSession", back_populates="messages")
