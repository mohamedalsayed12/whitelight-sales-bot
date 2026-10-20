import enum
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UserRole(str, enum.Enum):
    admin = "admin"
    manager = "manager"
    salesman = "salesman"


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        CheckConstraint(
            "role IN ('admin', 'manager', 'salesman')",
            name="ck_users_role",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(255))
    hashed_password: Mapped[str] = mapped_column(String(255))
    # Text, not a Postgres enum, so adding a role later is a normal migration.
    role: Mapped[UserRole] = mapped_column(
        SAEnum(
            UserRole,
            native_enum=False,
            length=20,
            values_callable=lambda members: [member.value for member in members],
        )
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        server_default=func.now(),
    )


def _text_enum(enum_cls: type[enum.Enum], length: int) -> SAEnum:
    # Text, not a Postgres enum, so adding a value later is a normal migration.
    return SAEnum(
        enum_cls,
        native_enum=False,
        length=length,
        values_callable=lambda members: [member.value for member in members],
    )


class ClientType(str, enum.Enum):
    hotel = "hotel"
    restaurant = "restaurant"
    other = "other"


class PriceListName(str, enum.Enum):
    hotel = "hotel"
    restaurant = "restaurant"


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("sku", name="uq_products_sku"),
        CheckConstraint("stock_on_hand >= 0", name="ck_products_stock_non_negative"),
        CheckConstraint("reorder_level >= 0", name="ck_products_reorder_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(100), default="")
    unit: Mapped[str] = mapped_column(String(32), default="pcs")
    # Tally quantities can be fractional. Numeric avoids float rounding.
    stock_on_hand: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=Decimal("0"))
    reorder_level: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=Decimal("0"))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Client(Base):
    __tablename__ = "clients"
    __table_args__ = (
        UniqueConstraint("name", name="uq_clients_name"),
        CheckConstraint(
            "type IN ('hotel', 'restaurant', 'other')",
            name="ck_clients_type",
        ),
        CheckConstraint(
            "price_list IS NULL OR price_list IN ('hotel', 'restaurant')",
            name="ck_clients_price_list",
        ),
        CheckConstraint("credit_limit >= 0", name="ck_clients_credit_limit_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    type: Mapped[ClientType] = mapped_column(_text_enum(ClientType, 20), default=ClientType.other)
    # Empty until a manager assigns hotel or restaurant prices.
    price_list: Mapped[PriceListName | None] = mapped_column(
        _text_enum(PriceListName, 20),
        nullable=True,
    )
    credit_limit: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=Decimal("0"))
    assigned_salesman_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    phone: Mapped[str] = mapped_column(String(50), default="")
    cr_number: Mapped[str | None] = mapped_column(String(50))


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("number", name="uq_invoices_number"),
        CheckConstraint("amount >= 0", name="ck_invoices_amount_non_negative"),
        CheckConstraint("amount_paid >= 0", name="ck_invoices_amount_paid_non_negative"),
        CheckConstraint("amount_paid <= amount", name="ck_invoices_paid_not_above_amount"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))
    number: Mapped[str] = mapped_column(String(64))
    # A calendar date has no time, so this is not a UTC timestamp.
    issue_date: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    amount_paid: Mapped[Decimal] = mapped_column(Numeric(12, 3))
