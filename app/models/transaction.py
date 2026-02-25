from decimal import Decimal
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class TransactionStatus(str, Enum):
    AUTHORIZED = "AUTHORIZED"
    CAPTURED = "CAPTURED"
    SETTLED = "SETTLED"
    VOIDED = "VOIDED"
    CHARGEBACKED = "CHARGEBACKED"


class PaymentMethodType(str, Enum):
    CARD = "CARD"
    WALLET = "WALLET"
    BANK_TRANSFER = "BANK_TRANSFER"
    CASH = "CASH"


class Item(BaseModel):
    model_config = {"extra": "forbid"}

    id: str = Field(..., min_length=1, max_length=50, pattern=r'^[A-Z0-9_-]+$')
    name: str = Field(..., min_length=1, max_length=200)
    unit_price: Decimal = Field(..., gt=Decimal("0"), le=Decimal("1000000.00"))
    quantity: int = Field(..., ge=1, le=10000)


class PaymentMethod(BaseModel):
    model_config = {"extra": "forbid"}

    id: str = Field(..., min_length=1, max_length=50)
    type: PaymentMethodType
    amount: Decimal = Field(..., gt=Decimal("0"), le=Decimal("1000000.00"))
    currency: str = Field(..., min_length=3, max_length=3)
    installments_total: Optional[int] = Field(None, ge=1, le=60)
    installments_charged: Optional[int] = Field(None, ge=0, le=60)
    card_last4: Optional[str] = Field(None, min_length=4, max_length=4, pattern=r'^\d{4}$')


class Transaction(BaseModel):
    model_config = {"extra": "forbid"}

    id: str = Field(..., min_length=1, max_length=50)
    status: TransactionStatus
    currency: str = Field(..., min_length=3, max_length=3)
    subtotal: Decimal = Field(..., ge=Decimal("0"), le=Decimal("1000000.00"))
    tax: Decimal = Field(..., ge=Decimal("0"), le=Decimal("1000000.00"))
    shipping: Decimal = Field(..., ge=Decimal("0"), le=Decimal("1000000.00"))
    total: Decimal = Field(..., gt=Decimal("0"), le=Decimal("1000000.00"))
    items: list[Item]
    payments: list[PaymentMethod]
    exchange_rate_to_usd: Optional[Decimal] = Field(None, gt=Decimal("0"))
    is_cross_border: bool = False
    merchant_id: str = Field(..., min_length=1, max_length=50)
