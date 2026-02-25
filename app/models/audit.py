from decimal import Decimal
from datetime import datetime
from typing import Optional, Literal, Any
from pydantic import BaseModel, Field


class AuditEntry(BaseModel):
    id: str
    timestamp: datetime
    refund_id: Optional[str] = None
    transaction_id: str
    operator_id: str
    action: Literal["REFUND_REQUESTED", "REFUND_APPROVED", "REFUND_REJECTED"]
    operation_type: Literal["REFUND"] = "REFUND"
    reasoning: str
    calculation_detail: dict[str, Any]
    amount: Optional[Decimal] = None
    currency: Optional[str] = None
    request_id: str
