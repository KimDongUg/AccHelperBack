from pydantic import BaseModel


class SubscriberItem(BaseModel):
    company_id: int
    company_name: str
    company_code: str
    subscription_plan: str
    billing_active: bool
    has_billing_key: bool
    card_company: str | None = None
    card_number: str | None = None
    admin_count: int = 0
    total_paid: int = 0
    payment_count: int = 0
    last_paid_at: str | None = None
    trial_ends_at: str | None = None
    created_at: str


class SubscriberListResponse(BaseModel):
    success: bool
    items: list[SubscriberItem] = []
    total: int = 0


class PaymentItem(BaseModel):
    id: int
    company_id: int
    company_name: str
    order_id: str
    order_name: str
    amount: int
    status: str
    payment_key: str | None = None
    failure_reason: str | None = None
    paid_at: str


class PaymentListResponse(BaseModel):
    success: bool
    items: list[PaymentItem] = []
    total: int = 0


class DashboardOverview(BaseModel):
    success: bool
    total_companies: int = 0
    active_subscribers: int = 0
    trial_subscribers: int = 0
    free_companies: int = 0
    total_revenue: int = 0
    total_payments: int = 0
