import enum
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
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


class ChequeStatus(str, enum.Enum):
    received = "received"
    deposited = "deposited"
    cleared = "cleared"
    bounced = "bounced"


class Cheque(Base):
    __tablename__ = "cheques"
    __table_args__ = (
        CheckConstraint(
            "status IN ('received', 'deposited', 'cleared', 'bounced')",
            name="ck_cheques_status",
        ),
        CheckConstraint("amount >= 0", name="ck_cheques_amount_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))
    cheque_number: Mapped[str] = mapped_column(String(64))
    bank: Mapped[str] = mapped_column(String(100))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    due_date: Mapped[date] = mapped_column(Date)
    status: Mapped[ChequeStatus] = mapped_column(_text_enum(ChequeStatus, 20))
    collected_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    # When the salesman logged the cheque. The daily summary uses this, in Asia/Bahrain.
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        server_default=func.now(),
    )


class PriceList(Base):
    __tablename__ = "price_lists"
    __table_args__ = (UniqueConstraint("name", name="uq_price_lists_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[PriceListName] = mapped_column(_text_enum(PriceListName, 20))


class PriceListItem(Base):
    __tablename__ = "price_list_items"
    __table_args__ = (
        UniqueConstraint("price_list_id", "product_id", name="uq_price_list_items_product"),
        CheckConstraint("unit_price > 0", name="ck_price_list_items_price_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    price_list_id: Mapped[int] = mapped_column(ForeignKey("price_lists.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 3))


class OrderStatus(str, enum.Enum):
    submitted = "submitted"
    approved = "approved"
    out_for_delivery = "out_for_delivery"
    delivered = "delivered"
    cancelled = "cancelled"


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint(
            "status IN ('submitted', 'approved', 'out_for_delivery', 'delivered', 'cancelled')",
            name="ck_orders_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))
    salesman_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[OrderStatus] = mapped_column(_text_enum(OrderStatus, 20))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        server_default=func.now(),
    )


class OrderLine(Base):
    __tablename__ = "order_lines"
    __table_args__ = (
        UniqueConstraint("order_id", "product_id", name="uq_order_lines_product"),
        CheckConstraint("quantity > 0", name="ck_order_lines_quantity_positive"),
        CheckConstraint("unit_price > 0", name="ck_order_lines_price_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    # Copied from the price list when the order is submitted.
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 3))


class Quote(Base):
    __tablename__ = "quotes"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))
    salesman_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    # The quote can be sent until this calendar date, inclusive.
    valid_until: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        server_default=func.now(),
    )


class QuoteLine(Base):
    __tablename__ = "quote_lines"
    __table_args__ = (
        UniqueConstraint("quote_id", "product_id", name="uq_quote_lines_product"),
        CheckConstraint("quantity > 0", name="ck_quote_lines_quantity_positive"),
        CheckConstraint("unit_price > 0", name="ck_quote_lines_price_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    quote_id: Mapped[int] = mapped_column(ForeignKey("quotes.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    # Copied from the price list when the quote is created.
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 3))


class OrderHistory(Base):
    __tablename__ = "order_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    status: Mapped[OrderStatus] = mapped_column(_text_enum(OrderStatus, 20))
    changed_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        server_default=func.now(),
    )


class LeadStatus(str, enum.Enum):
    new = "new"
    contacted = "contacted"
    quote_sent = "quote_sent"
    won = "won"


class LeadSource(str, enum.Enum):
    tender = "tender"
    exhibition = "exhibition"
    hand = "hand"
    referral = "referral"


class Lead(Base):
    """A business a salesman might call. Sample rows are fictional."""

    __tablename__ = "leads"
    __table_args__ = (
        CheckConstraint(
            "status IN ('new', 'contacted', 'quote_sent', 'won')",
            name="ck_leads_status",
        ),
        CheckConstraint(
            "source IN ('tender', 'exhibition', 'hand', 'referral')",
            name="ck_leads_source",
        ),
        CheckConstraint("score >= 0 AND score <= 100", name="ck_leads_score"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(50))
    area: Mapped[str] = mapped_column(String(80))
    summary: Mapped[str] = mapped_column(String(255))
    score: Mapped[int] = mapped_column(Integer)
    # JSON list of {points, text}. Shown on the lead, not recalculated.
    reasons: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[LeadStatus] = mapped_column(_text_enum(LeadStatus, 20))
    source: Mapped[LeadSource] = mapped_column(_text_enum(LeadSource, 20))
    phone: Mapped[str] = mapped_column(String(30), default="")
    pitch_hook: Mapped[str] = mapped_column(String(255), default="")
    contact_by: Mapped[date | None] = mapped_column(Date)
    quote_sent_on: Mapped[date | None] = mapped_column(Date)
    assigned_salesman_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    suggested_salesman_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        server_default=func.now(),
    )
