import enum
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from .database import Base


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


class UserCredentialsMixin:
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
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


class Admin(Base, UserCredentialsMixin):
    __tablename__ = "admins"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(180), nullable=False)
    phone = Column(String(30), nullable=False)
    authorization_level = Column(String(50), nullable=False, default="standard")
    is_superadmin = Column(Boolean, nullable=False, default=False)


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

    franchise_owner = relationship("FranchiseOwner", back_populates="supply_requests")


class Inventory(Base):
    __tablename__ = "inventories"

    id = Column(Integer, primary_key=True, index=True)
    franchise_owner_id = Column(Integer, ForeignKey("franchise_owners.id"), nullable=False)
    item_name = Column(String(255), nullable=False)
    stock_level = Column(Integer, nullable=False, default=0)

    franchise_owner = relationship("FranchiseOwner", back_populates="inventories")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    application_id = Column(Integer, ForeignKey("applications.id"), nullable=False, index=True)
    sender_role = Column(Enum(UserRole, name="message_sender_role"), nullable=False)
    sender_id = Column(Integer, nullable=False, index=True)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    application = relationship("Application", back_populates="messages")
