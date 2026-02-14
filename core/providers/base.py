"""
Base Payment Provider Interface

All payment providers must implement this interface for compatibility.
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional, Any, List
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class SubscriptionStatus(str, Enum):
    """Subscription status enumeration."""
    ACTIVE = "active"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    PAST_DUE = "past_due"
    TRIAL = "trial"
    UNPAID = "unpaid"


@dataclass
class Subscription:
    """Subscription data structure."""
    id: str
    user_id: str
    plan_id: str
    status: SubscriptionStatus
    current_period_start: datetime
    current_period_end: datetime
    cancel_at_period_end: bool = False
    credits_remaining: int = 0
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class PaymentResult:
    """Payment operation result."""
    success: bool
    message: str
    transaction_id: Optional[str] = None
    payment_url: Optional[str] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class License:
    """License key data structure."""
    key: str
    user_id: str
    plan_id: str
    created_at: datetime
    expires_at: Optional[datetime] = None
    is_active: bool = True
    credits: int = 0
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class BasePaymentProvider(ABC):
    """Abstract base class for all payment providers."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.name = self.__class__.__name__.replace("Provider", "").lower()
    
    @abstractmethod
    async def create_subscription(self, user_id: str, plan_id: str, customer_email: str,
                                  customer_name: Optional[str] = None,
                                  success_url: Optional[str] = None,
                                  cancel_url: Optional[str] = None) -> PaymentResult:
        pass
    
    @abstractmethod
    async def cancel_subscription(self, subscription_id: str) -> PaymentResult:
        pass
    
    @abstractmethod
    async def get_subscription(self, subscription_id: str) -> Optional[Subscription]:
        pass
    
    @abstractmethod
    async def purchase_credits(self, user_id: str, credit_pack_id: str, customer_email: str,
                               success_url: Optional[str] = None,
                               cancel_url: Optional[str] = None) -> PaymentResult:
        pass
    
    @abstractmethod
    async def verify_webhook(self, payload: str, signature: str) -> bool:
        pass
    
    @abstractmethod
    async def handle_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    def generate_license_key(self, user_id: str, plan_id: str) -> str:
        pass
    
    @abstractmethod
    async def validate_license(self, license_key: str) -> Optional[License]:
        pass
    
    @abstractmethod
    async def get_customer_portal_url(self, customer_id: str) -> Optional[str]:
        pass
    
    async def is_healthy(self) -> bool:
        return True
    
    def supports_subscriptions(self) -> bool:
        return True
    
    def supports_one_time_payments(self) -> bool:
        return True
    
    def requires_automatic_webhooks(self) -> bool:
        return True
