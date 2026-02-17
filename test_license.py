"""Test script to check license validation"""

import sys

sys.path.insert(0, ".")

from core.license_manager import get_license_manager
from datetime import datetime

lm = get_license_manager()

print("=== License Debug Info ===")
print(f"Current hardware fingerprint: {lm._hardware_fp}")
print(f"License file path: {lm.LICENSE_FILE}")
print(f"License file exists: {lm.LICENSE_FILE.exists()}")

if lm._current_license:
    print(f"\nStored license:")
    print(f"  Key: {lm._current_license.key}")
    print(f"  Stored hardware fingerprint: {lm._current_license.hardware_fingerprint}")
    print(f"  Is active: {lm._current_license.is_active}")
    print(
        f"  Hardware match: {lm._current_license.hardware_fingerprint == lm._hardware_fp}"
    )

    expires_at = datetime.fromisoformat(lm._current_license.expires_at)
    print(f"  Expires at: {expires_at}")
    print(f"  Expired: {datetime.utcnow() > expires_at}")

    if lm._current_license.offline_grace_period_end:
        grace_end = datetime.fromisoformat(lm._current_license.offline_grace_period_end)
        print(f"  Grace period end: {grace_end}")
        print(f"  In grace period: {datetime.utcnow() < grace_end}")
else:
    print("\nNo license loaded")

print(f"\nHas valid license: {lm.has_valid_license()}")
print(f"Has trial available: {lm.has_trial_available()}")
print(f"Can use app: {lm.can_use_app()}")

# Test hardware fingerprint components
print("\n=== Hardware Fingerprint Components ===")
import platform
import hashlib
import json

system_info = {
    "platform": platform.platform(),
    "machine": platform.machine(),
    "processor": platform.processor(),
    "node": platform.node(),
}
print(f"Platform: {system_info['platform']}")
print(f"Machine: {system_info['machine']}")
print(f"Processor: {system_info['processor']}")
print(f"Node: {system_info['node']}")

# Test UUID
try:
    import subprocess

    result = subprocess.run(
        ["wmic", "csproduct", "get", "uuid"], capture_output=True, text=True
    )
    uuid_val = result.stdout.strip().split("\n")[-1].strip()
    print(f"UUID: {uuid_val}")
except Exception as e:
    print(f"UUID error: {e}")
