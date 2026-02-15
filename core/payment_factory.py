"""
Payment Factory Module

Unified interface for all payment providers.
Switch providers by changing PAYMENT_PROVIDER in config.
"""

from typing import Optional, Type
import os

from config.payment_config import (
    PaymentProvider,
    PAYMENT_PROVIDER,
    payment_settings,
    pricing_config,
)
from core.providers.base import BasePaymentProvider


class PaymentProcessor:
    """
    Unified payment processor that auto-detects and uses the configured provider.

    Usage:
        from core.payment_factory import PaymentProcessor

        payment = PaymentProcessor()

        # Create subscription
        result = await payment.create_subscription(
            user_id="user_123",
            plan_id="pro",
            customer_email="user@example.com"
        )

        # Validate license
        license = await payment.validate_license(license_key)
        if license:
            allow_access()
    """

    def __init__(self, provider: Optional[PaymentProvider] = None):
        """
        Initialize payment processor.

        Args:
            provider: Override the default provider from config
        """
        self.provider_name = provider or PAYMENT_PROVIDER
        self._provider: Optional[BasePaymentProvider] = None
        self._initialize_provider()

    def _initialize_provider(self):
        """Initialize the selected payment provider."""
        provider_class = self._get_provider_class(self.provider_name)

        if provider_class:
            self._provider = provider_class()
        else:
            raise ValueError(f"Unknown payment provider: {self.provider_name}")

    def _get_provider_class(
        self, provider: PaymentProvider
    ) -> Optional[Type[BasePaymentProvider]]:
        """Get provider class based on name."""
        from core.providers.gumroad import GumroadProvider
        from core.providers.razorpay import RazorpayProvider

        provider_map = {
            PaymentProvider.GUMROAD: GumroadProvider,
            PaymentProvider.RAZORPAY: RazorpayProvider,
            # Add more providers here as they're implemented
            # PaymentProvider.STRIPE: StripeProvider,
            # PaymentProvider.LEMONSQUEEZY: LemonSqueezyProvider,
            # PaymentProvider.PAYPAL: PayPalProvider,
        }

        return provider_map.get(provider)

    @property
    def provider(self) -> BasePaymentProvider:
        """Get the underlying provider instance."""
        if not self._provider:
            self._initialize_provider()
        return self._provider

    # ═════════════════════════════════════════════════════════════════
    # Proxy methods to provider
    # ═════════════════════════════════════════════════════════════════

    async def create_subscription(self, *args, **kwargs):
        """Create a subscription."""
        return await self.provider.create_subscription(*args, **kwargs)

    async def cancel_subscription(self, *args, **kwargs):
        """Cancel a subscription."""
        return await self.provider.cancel_subscription(*args, **kwargs)

    async def get_subscription(self, *args, **kwargs):
        """Get subscription details."""
        return await self.provider.get_subscription(*args, **kwargs)

    async def purchase_credits(self, *args, **kwargs):
        """Purchase credits."""
        return await self.provider.purchase_credits(*args, **kwargs)

    async def verify_webhook(self, *args, **kwargs):
        """Verify webhook signature."""
        return await self.provider.verify_webhook(*args, **kwargs)

    async def handle_webhook(self, *args, **kwargs):
        """Handle webhook event."""
        return await self.provider.handle_webhook(*args, **kwargs)

    def generate_license_key(self, *args, **kwargs):
        """Generate license key."""
        return self.provider.generate_license_key(*args, **kwargs)

    async def validate_license(self, license_key: str, *args, **kwargs):
        """Validate license key."""
        from datetime import datetime
        from core.providers.base import License

        # Check for admin/master licenses first (hardcoded, works across all providers)
        admin_licenses = {
            "I3D-ADMIN-LIFETIME-2026": License(
                key="I3D-ADMIN-LIFETIME-2026",
                user_id="admin",
                plan_id="lifetime",
                credits=999999,
                created_at=datetime.utcnow(),
                expires_at=None,
                is_active=True,
                metadata={"type": "admin", "description": "Admin lifetime license"},
            ),
            "I3D-MASTER-UNLIMITED": License(
                key="I3D-MASTER-UNLIMITED",
                user_id="master",
                plan_id="unlimited",
                credits=999999,
                created_at=datetime.utcnow(),
                expires_at=None,
                is_active=True,
                metadata={"type": "master", "description": "Master unlimited license"},
            ),
        }

        # Check admin licenses (case-insensitive)
        license_key_upper = license_key.upper()
        if license_key_upper in admin_licenses:
            return admin_licenses[license_key_upper]

        # Fall back to provider validation
        return await self.provider.validate_license(license_key, *args, **kwargs)

    async def get_customer_portal_url(self, *args, **kwargs):
        """Get customer portal URL."""
        return await self.provider.get_customer_portal_url(*args, **kwargs)

    # ═════════════════════════════════════════════════════════════════
    # Convenience methods
    # ═════════════════════════════════════════════════════════════════

    def get_current_provider_name(self) -> str:
        """Get name of current provider."""
        return self.provider_name.value

    def get_provider_info(self) -> dict:
        """Get information about current provider."""
        info = {
            PaymentProvider.GUMROAD: {
                "name": "Gumroad",
                "fees": "10% per transaction",
                "registration_required": False,
                "best_for": "Quick start without registration",
            },
            PaymentProvider.RAZORPAY: {
                "name": "Razorpay",
                "fees": "2-3% per transaction",
                "registration_required": True,
                "best_for": "Indian businesses with GST",
            },
            PaymentProvider.STRIPE: {
                "name": "Stripe",
                "fees": "2-3% per transaction",
                "registration_required": True,
                "best_for": "International businesses",
            },
        }
        return info.get(self.provider_name, {})

    def get_plan_details(self, plan_id: str) -> dict:
        """Get plan details including pricing."""
        plan = pricing_config.plans.get(plan_id, {})
        return {
            "id": plan_id,
            "name": plan.get("name"),
            "price": plan.get("price"),
            "currency": payment_settings.currency,
            "credits_per_month": plan.get("credits_per_month"),
            "features": plan.get("features", []),
        }

    def get_credit_pack_details(self, pack_id: str) -> dict:
        """Get credit pack details."""
        pack = pricing_config.credit_packs.get(pack_id, {})
        return {
            "id": pack_id,
            "name": pack.get("name"),
            "price": pack.get("price"),
            "currency": payment_settings.currency,
            "credits": pack.get("credits"),
        }

    def list_available_plans(self) -> list:
        """List all available subscription plans."""
        return [
            self.get_plan_details(plan_id) for plan_id in pricing_config.plans.keys()
        ]

    def list_available_credit_packs(self) -> list:
        """List all available credit packs."""
        return [
            self.get_credit_pack_details(pack_id)
            for pack_id in pricing_config.credit_packs.keys()
        ]

    async def check_credit_balance(self, license_key: str) -> dict:
        """Check remaining credits for a license."""
        license_obj = await self.validate_license(license_key)

        if not license_obj:
            return {
                "valid": False,
                "credits": 0,
                "message": "Invalid or expired license",
            }

        return {
            "valid": True,
            "credits": license_obj.credits,
            "plan_id": license_obj.plan_id,
            "expires_at": license_obj.expires_at.isoformat()
            if license_obj.expires_at
            else None,
        }

    async def deduct_credits(
        self, license_key: str, amount: int, operation: str
    ) -> dict:
        """
        Deduct credits from license.

        Args:
            license_key: License key
            amount: Credits to deduct
            operation: Operation type (for logging)

        Returns:
            dict with success status and remaining credits
        """
        license_obj = await self.validate_license(license_key)

        if not license_obj:
            return {
                "success": False,
                "message": "Invalid or expired license",
                "remaining_credits": 0,
            }

        if license_obj.credits < amount:
            return {
                "success": False,
                "message": f"Insufficient credits. Required: {amount}, Available: {license_obj.credits}",
                "remaining_credits": license_obj.credits,
            }

        # Deduct credits
        license_obj.credits -= amount

        return {
            "success": True,
            "message": f"Deducted {amount} credits for {operation}",
            "remaining_credits": license_obj.credits,
            "operation": operation,
        }

    async def close(self):
        """Close provider connections."""
        if hasattr(self.provider, "close"):
            await self.provider.close()


# Convenience function
def get_payment_processor(
    provider: Optional[PaymentProvider] = None,
) -> PaymentProcessor:
    """Get configured payment processor instance."""
    return PaymentProcessor(provider)


__all__ = ["PaymentProcessor", "get_payment_processor"]
