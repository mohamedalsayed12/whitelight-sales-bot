from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.models import ChequeStatus, OrderStatus, PriceListName, UserRole
from app.services.accounts import AccountStatus
from app.services.passwords import validate_password


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr = Field(max_length=255)
    full_name: str = Field(min_length=1, max_length=255)
    password: str

    @field_validator("full_name")
    @classmethod
    def strip_full_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Full name is required")
        return cleaned

    @field_validator("password")
    @classmethod
    def check_password(cls, value: str) -> str:
        return validate_password(value)


class AdminUserCreate(UserCreate):
    role: UserRole


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    role: UserRole
    created_at: datetime


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr = Field(max_length=255)
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class HealthResponse(BaseModel):
    status: str
    database: str


class ImportRowError(BaseModel):
    row: int
    message: str


class ImportResultOut(BaseModel):
    imported: int
    failed: int
    errors: list[ImportRowError]


class StockItem(BaseModel):
    sku: str
    name: str
    unit: str
    available: Decimal
    low_stock: bool


class OverdueOut(BaseModel):
    # JSON keys match the aging buckets: 0-30, 31-60, 61-90, and more than 90.
    days_0_30: Decimal = Field(serialization_alias="0_30")
    days_31_60: Decimal = Field(serialization_alias="31_60")
    days_61_90: Decimal = Field(serialization_alias="61_90")
    over_90: Decimal = Field(serialization_alias="over_90")


class ClientAccountOut(BaseModel):
    client_id: int
    name: str
    total_outstanding: Decimal
    overdue: OverdueOut
    pending_cheques: Decimal
    status: AccountStatus


def _three_places(value: Decimal, field_name: str) -> Decimal:
    if not value.is_finite():
        raise ValueError(f"{field_name} must be a number")
    exponent = value.as_tuple().exponent
    if isinstance(exponent, int) and exponent < -3:
        raise ValueError(f"{field_name} can have at most 3 decimal places")
    return value.quantize(Decimal("0.001"))


class PriceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku: str = Field(min_length=1, max_length=64)
    unit_price: Decimal

    @field_validator("unit_price")
    @classmethod
    def check_price(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("unit_price must be greater than 0")
        return _three_places(value, "unit_price")


class ClientTermsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    price_list: PriceListName | None = None
    credit_limit: Decimal | None = None

    @field_validator("credit_limit")
    @classmethod
    def check_limit(cls, value: Decimal | None) -> Decimal | None:
        if value is None:
            return None
        if value < 0:
            raise ValueError("credit_limit cannot be negative")
        return _three_places(value, "credit_limit")

    @model_validator(mode="after")
    def at_least_one_field(self) -> "ClientTermsUpdate":
        if self.price_list is None and self.credit_limit is None:
            raise ValueError("Set price_list or credit_limit")
        return self


class ClientTermsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    price_list: PriceListName | None
    credit_limit: Decimal


class OrderLineIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku: str = Field(min_length=1, max_length=64)
    quantity: Decimal

    @field_validator("sku")
    @classmethod
    def strip_sku(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("sku is required")
        return cleaned

    @field_validator("quantity")
    @classmethod
    def check_quantity(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("quantity must be greater than 0")
        return _three_places(value, "quantity")


class OrderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_id: int
    lines: list[OrderLineIn] = Field(min_length=1)

    @field_validator("lines")
    @classmethod
    def unique_skus(cls, lines: list[OrderLineIn]) -> list[OrderLineIn]:
        seen: set[str] = set()
        for line in lines:
            if line.sku in seen:
                raise ValueError(f"duplicate sku {line.sku}")
            seen.add(line.sku)
        return lines


class OrderLineOut(BaseModel):
    sku: str
    quantity: Decimal
    unit_price: Decimal


class OrderHistoryOut(BaseModel):
    status: OrderStatus
    changed_by_id: int
    changed_at: datetime


class OrderOut(BaseModel):
    id: int
    client_id: int
    salesman_id: int
    status: OrderStatus
    warning: str | None
    lines: list[OrderLineOut]
    history: list[OrderHistoryOut]


class OrderStatusChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: OrderStatus


class QuoteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_id: int
    valid_until: date
    lines: list[OrderLineIn] = Field(min_length=1)

    @field_validator("lines")
    @classmethod
    def unique_skus(cls, lines: list[OrderLineIn]) -> list[OrderLineIn]:
        seen: set[str] = set()
        for line in lines:
            if line.sku in seen:
                raise ValueError(f"duplicate sku {line.sku}")
            seen.add(line.sku)
        return lines


class QuoteLineOut(BaseModel):
    sku: str
    quantity: Decimal
    unit_price: Decimal


class QuoteOut(BaseModel):
    id: int
    client_id: int
    salesman_id: int
    valid_until: date
    total: Decimal
    lines: list[QuoteLineOut]


class ChequeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_id: int
    cheque_number: str = Field(min_length=1, max_length=64)
    bank: str = Field(min_length=1, max_length=100)
    amount: Decimal
    due_date: date

    @field_validator("cheque_number", "bank")
    @classmethod
    def strip_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("this field is required")
        return cleaned

    @field_validator("amount")
    @classmethod
    def check_amount(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("amount must be greater than 0")
        return _three_places(value, "amount")


class ChequeStatusChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ChequeStatus


class ChequeOut(BaseModel):
    id: int
    client_id: int
    client_name: str
    cheque_number: str
    bank: str
    amount: Decimal
    due_date: date
    status: ChequeStatus
    collected_by_id: int | None


class ReorderItemOut(BaseModel):
    sku: str
    name: str
    stock_on_hand: Decimal
    available: Decimal
    reorder_level: Decimal
    on_order: Decimal


class DailySummaryOut(BaseModel):
    day: date
    orders_today: int
    orders_total: Decimal
    cheques_collected: Decimal
    total_overdue: Decimal
    reorder: list[ReorderItemOut]
