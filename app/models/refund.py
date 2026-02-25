from decimal import Decimal
from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, Field


class RefundRequest(BaseModel):
    model_config = {"extra": "forbid"}

    transaction_id: str = Field(..., min_length=1, max_length=50, pattern=r'^[A-Z0-9_-]+$')
    item_ids: Optional[list[str]] = Field(None, max_length=100)
    operator_id: str = Field(..., min_length=1, max_length=50, pattern=r'^[a-zA-Z0-9_-]+$')
    reason: str = Field(..., min_length=1, max_length=500)
    idempotency_key: Optional[str] = Field(None, min_length=1, max_length=100)


class PaymentRefund(BaseModel):
    payment_id: str
    payment_type: str
    original_amount: Decimal
    refund_amount: Decimal
    currency: str


class CalculationBreakdown(BaseModel):
    scenario: str
    items_subtotal: Optional[Decimal] = None
    item_ratio: Optional[Decimal] = None
    proportional_tax: Optional[Decimal] = None
    proportional_shipping: Optional[Decimal] = None
    total_refund: Decimal
    payment_breakdown: list[PaymentRefund]
    usd_equivalent: Optional[Decimal] = None
    exchange_rate_used: Optional[Decimal] = None
    installments_charged: Optional[int] = None
    installments_total: Optional[int] = None
    installment_value: Optional[Decimal] = None
    charged_amount: Optional[Decimal] = None


class RefundResult(BaseModel):
    refund_id: str
    operation_type: Literal["REFUND"] = "REFUND"
    transaction_id: str
    status: str
    total_refund_amount: Decimal
    currency: str
    operator_id: str
    reason: str
    calculation_breakdown: CalculationBreakdown
    created_at: datetime
    idempotency_key: Optional[str] = None
