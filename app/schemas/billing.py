from pydantic import BaseModel


class BillingPayRequest(BaseModel):
    company_id: int
    amount: int | None = None  # None이면 서버에서 업체 수 기반 자동 계산
    order_name: str = "보듬누리 구독"


class BillingPayResponse(BaseModel):
    success: bool
    message: str
    payment_key: str | None = None
    order_id: str | None = None
    amount: int | None = None


class BillingStatusResponse(BaseModel):
    success: bool
    active: bool = False
    has_billing_key: bool = False
    card_company: str | None = None
    card_number: str | None = None
    subscription_plan: str | None = None
    trial_ends_at: str | None = None


class BillingTrialResponse(BaseModel):
    success: bool
    message: str
    trial_ends_at: str | None = None


class BillingCancelResponse(BaseModel):
    success: bool
    message: str


class BillingKeyDeactivateResponse(BaseModel):
    success: bool
    message: str


class PaymentHistoryItem(BaseModel):
    order_id: str
    order_name: str
    amount: int
    status: str
    payment_key: str | None = None
    failure_reason: str | None = None
    paid_at: str


class PaymentHistoryResponse(BaseModel):
    success: bool
    payments: list[PaymentHistoryItem] = []
