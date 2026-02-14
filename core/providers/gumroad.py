"""
Gumroad Payment Provider Implementation

Best for: Quick start without business registration
Requirements: No GST/PAN needed
Fees: 10% per transaction
"""

import os
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Dict, Optional, Any
import httpx

from core.providers.base import (
    BasePaymentProvider, Subscription, PaymentResult, 
    License, SubscriptionStatus
)
from config.payment_config import gumroad_config, pricing_config, payment_settings


class GumroadProvider(BasePaymentProvider):
    """
    Gumroad payment provider implementation.
    
    Gumroad acts as the merchant of record, handling all tax compliance.
    Perfect for starting without business registration.
    """
    
    BASE_URL = "https://api.gumroad.com/v2"
    
    def __init__(self, config: Optional[Dict] = None):
        super().__init__(config or {})
        self.access_token = os.getenv("GUMROAD_ACCESS_TOKEN") or gumroad_config.access_token
        self.client = httpx.AsyncClient(base_url=self.BASE_URL)
        self._licenses_db: Dict[str, License] = {}  # In-memory store for demo
    
    async def _make_request(self, method: str, endpoint: str, data: Dict = None) -> Dict:
        """Make authenticated request to Gumroad API."""
        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        if method == "GET":
            response = await self.client.get(endpoint, headers=headers, params=data)
        else:
            response = await self.client.post(endpoint, headers=headers, data=data)
        
        response.raise_for_status()
        return response.json()
    
    async def create_subscription(
        self,
        user_id: str,
        plan_id: str,
        customer_email: str,
        customer_name: Optional[str] = None,
        success_url: Optional[str] = None,
        cancel_url: Optional[str] = None,
    ) -> PaymentResult:
        """
        Create a Gumroad subscription.
        
        Note: Gumroad uses product-based subscriptions.
        Customer purchases a product that grants access.
        """
        try:
            # Map plan_id to Gumroad product
            product_mapping = {
                "starter": gumroad_config.product_ids.get("starter_monthly"),
                "pro": gumroad_config.product_ids.get("pro_monthly"),
                "enterprise": gumroad_config.product_ids.get("enterprise_monthly"),
            }
            
            product_id = product_mapping.get(plan_id)
            if not product_id:
                return PaymentResult(
                    success=False,
                    message=f"Product not configured for plan: {plan_id}"
                )
            
            # Generate unique license key
            license_key = self.generate_license_key(user_id, plan_id)
            
            # Create Gumroad offer code for this customer (optional)
            # Or redirect to product page with custom params
            product_url = f"https://gumroad.com/l/{product_id}"
            
            # Add custom parameters for tracking
            checkout_url = f"{product_url}?email={customer_email}&ref={user_id}"
            
            return PaymentResult(
                success=True,
                message="Redirect to Gumroad checkout",
                payment_url=checkout_url,
                metadata={
                    "license_key": license_key,
                    "product_id": product_id,
                    "plan_id": plan_id,
                }
            )
            
        except Exception as e:
            return PaymentResult(
                success=False,
                message=f"Failed to create subscription: {str(e)}"
            )
    
    async def cancel_subscription(self, subscription_id: str) -> PaymentResult:
        """
        Cancel a Gumroad subscription.
        
        In Gumroad, users cancel from their library or via customer portal.
        We track the cancellation via webhook.
        """
        # Gumroad doesn't have API for canceling subscriptions
        # Users must cancel from their Gumroad library
        return PaymentResult(
            success=True,
            message="User must cancel from Gumroad library. Webhook will update status.",
            metadata={"subscription_id": subscription_id}
        )
    
    async def get_subscription(self, subscription_id: str) -> Optional[Subscription]:
        """Get subscription details from Gumroad."""
        try:
            # Query Gumroad for sale/subscription details
            result = await self._make_request(
                "GET",
                f"/sales/{subscription_id}"
            )
            
            sale = result.get("sale", {})
            if not sale:
                return None
            
            # Determine status
            is_subscription = sale.get("is_subscription", False)
            is_cancelled = sale.get("subscription_cancelled_at") is not None
            
            if is_cancelled:
                status = SubscriptionStatus.CANCELLED
            elif is_subscription:
                status = SubscriptionStatus.ACTIVE
            else:
                status = SubscriptionStatus.ACTIVE
            
            created_at = datetime.fromisoformat(sale.get("created_at", "").replace("Z", "+00:00"))
            
            return Subscription(
                id=subscription_id,
                user_id=sale.get("custom_fields", {}).get("user_id", ""),
                plan_id=self._map_product_to_plan(sale.get("product_id", "")),
                status=status,
                current_period_start=created_at,
                current_period_end=created_at + timedelta(days=30),
                metadata=sale
            )
            
        except Exception:
            return None
    
    async def purchase_credits(
        self,
        user_id: str,
        credit_pack_id: str,
        customer_email: str,
        success_url: Optional[str] = None,
        cancel_url: Optional[str] = None,
    ) -> PaymentResult:
        """Purchase a credit pack via Gumroad."""
        product_mapping = {
            "small": gumroad_config.product_ids.get("credits_small"),
            "medium": gumroad_config.product_ids.get("credits_medium"),
            "large": gumroad_config.product_ids.get("credits_large"),
        }
        
        product_id = product_mapping.get(credit_pack_id)
        if not product_id:
            return PaymentResult(
                success=False,
                message=f"Product not configured for credit pack: {credit_pack_id}"
            )
        
        # Get credit amount
        credits = pricing_config.credit_packs.get(credit_pack_id, {}).get("credits", 0)
        
        product_url = f"https://gumroad.com/l/{product_id}"
        checkout_url = f"{product_url}?email={customer_email}&ref={user_id}"
        
        return PaymentResult(
            success=True,
            message="Redirect to Gumroad checkout for credits",
            payment_url=checkout_url,
            metadata={
                "credits": credits,
                "credit_pack_id": credit_pack_id,
            }
        )
    
    async def verify_webhook(self, payload: str, signature: str) -> bool:
        """
        Verify Gumroad webhook signature.
        
        Gumroad uses basic verification via signature in headers.
        """
        # Gumroad webhooks don't use signatures by default
        # They use IP filtering and HTTPS
        # For additional security, verify the webhook secret
        expected_secret = payment_settings.webhook_secret
        if expected_secret:
            return signature == expected_secret
        return True
    
    async def handle_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle Gumroad webhook events.
        
        Key events:
        - sale: New purchase
        - refund: Refund issued
        - subscription_cancelled: Subscription cancelled
        - subscription_restarted: Subscription restarted
        """
        event_type = payload.get("action")
        
        if event_type == "sale":
            return await self._handle_sale(payload)
        elif event_type == "refund":
            return await self._handle_refund(payload)
        elif event_type == "subscription_cancelled":
            return await self._handle_subscription_cancelled(payload)
        elif event_type == "subscription_restarted":
            return await self._handle_subscription_restarted(payload)
        
        return {"status": "ignored", "event": event_type}
    
    async def _handle_sale(self, payload: Dict) -> Dict[str, Any]:
        """Handle new sale event."""
        sale = payload.get("sale", {})
        product_id = sale.get("product_id")
        email = sale.get("email")
        custom_fields = sale.get("custom_fields", {})
        user_id = custom_fields.get("user_id", email)  # Fallback to email
        
        # Map product to plan
        plan_id = self._map_product_to_plan(product_id)
        
        # Generate license
        license_key = self.generate_license_key(user_id, plan_id)
        
        # Determine credits based on product
        credits = self._get_credits_for_product(product_id)
        
        # Store license
        license_obj = License(
            key=license_key,
            user_id=user_id,
            plan_id=plan_id,
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(days=30),
            is_active=True,
            credits=credits,
            metadata={
                "sale_id": sale.get("id"),
                "product_id": product_id,
                "email": email,
            }
        )
        self._licenses_db[license_key] = license_obj
        
        return {
            "status": "success",
            "event": "sale",
            "license_key": license_key,
            "user_id": user_id,
            "plan_id": plan_id,
            "credits": credits,
        }
    
    async def _handle_refund(self, payload: Dict) -> Dict[str, Any]:
        """Handle refund event."""
        sale = payload.get("sale", {})
        # Deactivate license associated with this sale
        sale_id = sale.get("id")
        
        for license_key, license_obj in self._licenses_db.items():
            if license_obj.metadata.get("sale_id") == sale_id:
                license_obj.is_active = False
                return {
                    "status": "success",
                    "event": "refund",
                    "license_deactivated": license_key,
                }
        
        return {"status": "not_found", "event": "refund"}
    
    async def _handle_subscription_cancelled(self, payload: Dict) -> Dict[str, Any]:
        """Handle subscription cancellation."""
        sale = payload.get("sale", {})
        # Mark license to expire at period end
        sale_id = sale.get("id")
        
        for license_key, license_obj in self._licenses_db.items():
            if license_obj.metadata.get("sale_id") == sale_id:
                # License remains active until period end
                license_obj.metadata["cancel_at_period_end"] = True
                return {
                    "status": "success",
                    "event": "subscription_cancelled",
                    "license_key": license_key,
                }
        
        return {"status": "not_found", "event": "subscription_cancelled"}
    
    async def _handle_subscription_restarted(self, payload: Dict) -> Dict[str, Any]:
        """Handle subscription restart."""
        sale = payload.get("sale", {})
        sale_id = sale.get("id")
        
        for license_key, license_obj in self._licenses_db.items():
            if license_obj.metadata.get("sale_id") == sale_id:
                license_obj.metadata["cancel_at_period_end"] = False
                # Extend expiry
                license_obj.expires_at = datetime.utcnow() + timedelta(days=30)
                return {
                    "status": "success",
                    "event": "subscription_restarted",
                    "license_key": license_key,
                }
        
        return {"status": "not_found", "event": "subscription_restarted"}
    
    def generate_license_key(self, user_id: str, plan_id: str) -> str:
        """Generate a unique license key."""
        prefix = payment_settings.license_key_prefix
        unique_string = f"{user_id}:{plan_id}:{secrets.token_hex(16)}"
        hash_part = hashlib.sha256(unique_string.encode()).hexdigest()[:24].upper()
        return f"{prefix}-{hash_part[:4]}-{hash_part[4:8]}-{hash_part[8:12]}-{hash_part[12:16]}"
    
    async def validate_license(self, license_key: str) -> Optional[License]:
        """Validate a license key."""
        license_obj = self._licenses_db.get(license_key)
        
        if not license_obj:
            return None
        
        if not license_obj.is_active:
            return None
        
        # Check expiry
        if license_obj.expires_at and license_obj.expires_at < datetime.utcnow():
            license_obj.is_active = False
            return None
        
        return license_obj
    
    async def get_customer_portal_url(self, customer_id: str) -> Optional[str]:
        """
        Get Gumroad customer library URL.
        
        Customers manage subscriptions from their Gumroad library.
        """
        return "https://app.gumroad.com/library"
    
    def _map_product_to_plan(self, product_id: str) -> str:
        """Map Gumroad product ID to internal plan ID."""
        reverse_mapping = {
            gumroad_config.product_ids.get("starter_monthly"): "starter",
            gumroad_config.product_ids.get("pro_monthly"): "pro",
            gumroad_config.product_ids.get("enterprise_monthly"): "enterprise",
            gumroad_config.product_ids.get("credits_small"): "credits_small",
            gumroad_config.product_ids.get("credits_medium"): "credits_medium",
            gumroad_config.product_ids.get("credits_large"): "credits_large",
        }
        return reverse_mapping.get(product_id, "unknown")
    
    def _get_credits_for_product(self, product_id: str) -> int:
        """Get credit amount for a product."""
        plan_id = self._map_product_to_plan(product_id)
        
        # Check if it's a subscription plan
        plan = pricing_config.plans.get(plan_id)
        if plan:
            return plan.get("credits_per_month", 0)
        
        # Check if it's a credit pack
        credit_pack = pricing_config.credit_packs.get(plan_id)
        if credit_pack:
            return credit_pack.get("credits", 0)
        
        return 0
    
    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()
