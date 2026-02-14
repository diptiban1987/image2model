#!/usr/bin/env python3
"""
ImageTo3D Pro - Trial & License Workflow Demo
Shows the complete user workflow without requiring heavy dependencies
"""

import sys
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.license_manager import get_license_manager

def print_box(text, width=60):
    """Print text in a box"""
    print('=' * width)
    for line in text.split('\n'):
        print(f'  {line:<{width-4}}')
    print('=' * width)

def show_trial_dialog():
    """Show the trial offer dialog"""
    print("""
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║           🚀 Welcome to ImageTo3D Pro                        ║
║                                                              ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║     🎉 You have 1 FREE generation remaining!                 ║
║                                                              ║
║     Try ImageTo3D Pro with no commitment.                    ║
║     Generate your first 3D model for FREE.                   ║
║                                                              ║
║     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━   ║
║                                                              ║
║     [🚀 START FREE TRIAL]                                    ║
║                                                              ║
║              - OR -                                          ║
║                                                              ║
║     [🛒 PURCHASE LICENSE NOW]                                ║
║                                                              ║
║     Available Plans:                                         ║
║     • Starter: ₹499/mo  • Pro: ₹999/mo                       ║
║                                                              ║
║     💡 After your free generation, you'll need               ║
║        a license to continue.                                ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
    """)

def show_license_dialog():
    """Show the license required dialog"""
    print("""
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║           ImageTo3D Pro - Get Started                        ║
║                                                              ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║     ✅ You've used your free trial!                          ║
║                                                              ║
║     Ready for more? Enter your license key                   ║
║     or purchase one below.                                   ║
║                                                              ║
║     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━   ║
║                                                              ║
║     Enter License Key:                                       ║
║     [                                        ]               ║
║     Example: I3D-ADB1-9890-4517-8E0F                         ║
║                                                              ║
║     [✓ VALIDATE LICENSE]    [🛒 PURCHASE LICENSE]            ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
    """)

def show_main_app():
    """Show the main app interface"""
    print("""
╔══════════════════════════════════════════════════════════════╗
║  Image → 3D Pro                                    [Logout]  ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  Source Image                                                ║
║  ┌──────────────────────────────────────────────────────┐   ║
║  │  Path: [image.jpg                        ] [Browse…] │   ║
║  └──────────────────────────────────────────────────────┘   ║
║                                                              ║
║  Processing Options                                          ║
║  ┌──────────────────────────────────────────────────────┐   ║
║  │  Method: (*) Local Processing    ( ) Hitem3D API     │   ║
║  │  Mesh quality: [Standard ▼]                          │   ║
║  └──────────────────────────────────────────────────────┘   ║
║                                                              ║
║  Preview                                                     ║
║  ┌──────────────────────────────────────────────────────┐   ║
║  │                                                      │   ║
║  │              [Image Preview Area]                    │   ║
║  │                                                      │   ║
║  └──────────────────────────────────────────────────────┘   ║
║                                                              ║
║  Status                                                      ║
║  ┌──────────────────────────────────────────────────────┐   ║
║  │  Idle                                                │   ║
║  │  [..............................................] 0% │   ║
║  └──────────────────────────────────────────────────────┘   ║
║                                                              ║
║  [Generate 3D Model]  [Reset]  [Open Output Folder]          ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
    """)

def simulate_workflow():
    """Simulate the complete user workflow"""
    lm = get_license_manager()
    
    print("\n" + "="*60)
    print("  📱 ImageTo3D Pro - Workflow Demonstration")
    print("="*60)
    print()
    
    # Check trial status
    print("CHECKING TRIAL STATUS...")
    print(f"  Trial available: {lm.has_trial_available()}")
    print(f"  Trial remaining: {lm.get_trial_remaining()}")
    print()
    
    input("Press ENTER to start the workflow demonstration...")
    print()
    
    # Step 1: Show trial dialog
    print("📱 STEP 1: First Launch - Trial Offer Dialog")
    print("-" * 60)
    show_trial_dialog()
    input("Press ENTER to click 'Start Free Trial'...")
    print()
    
    # Step 2: Activate trial
    print("👤 USER ACTION: Clicking 'Start Free Trial'...")
    if lm.use_trial_generation():
        print("✅ Trial activated successfully!")
        print(f"   Remaining: {lm.get_trial_remaining()}")
    print()
    
    # Step 3: Show main app
    print("📱 STEP 2: Main App Interface Opens")
    print("-" * 60)
    show_main_app()
    input("Press ENTER to generate a 3D model...")
    print()
    
    # Step 4: Generate model
    print("📱 STEP 3: User Generates 3D Model")
    print("-" * 60)
    print("⏳ Processing: [███████░░░░░░░░░░░░░░░░░░░] 35%")
    print("⏳ Processing: [████████████░░░░░░░░░░░░░░░] 50%")
    print("⏳ Processing: [█████████████████░░░░░░░░░░] 75%")
    print("✅ Generation complete! 3D model saved to output/")
    print("   Files created: model.obj, model.glb, model.stl")
    print()
    
    # Step 5: Check trial consumed
    print("📱 STEP 4: Trial Consumed - Check Status")
    print("-" * 60)
    print(f"   Trial available: {lm.has_trial_available()}")
    print(f"   Trial remaining: {lm.get_trial_remaining()}")
    print()
    
    # Step 6: Show license dialog
    print("📱 STEP 5: Second Launch - License Required")
    print("-" * 60)
    show_license_dialog()
    input("Press ENTER to purchase a license...")
    print()
    
    # Step 7: Purchase flow
    print("📱 STEP 6: Purchase Flow")
    print("-" * 60)
    print("👤 USER ACTION: Clicking 'Purchase License'...")
    print("🌐 Browser opens: https://gumroad.com/imageto3d")
    print("💳 User selects Pro plan (₹999/mo, 300 credits)")
    print("💳 Payment completed successfully!")
    print("📧 License key sent via email: I3D-ADB1-9890-4517-8E0F")
    print()
    
    # Step 8: Activate license
    print("📱 STEP 7: License Activation")
    print("-" * 60)
    print("👤 USER ACTION: Entering license key...")
    print("   Key: I3D-ADB1-9890-4517-8E0F")
    print("👤 USER ACTION: Clicking 'Validate License'...")
    print("✅ License validated successfully!")
    print("   Plan: pro")
    print("   Credits: 300")
    print()
    
    # Step 9: Full access
    print("📱 STEP 8: Full Access Unlocked! 🎉")
    print("-" * 60)
    print("✅ User can now generate unlimited 3D models")
    print("✅ All features unlocked")
    print("✅ 300 credits available for API usage")
    print("✅ Priority support enabled")
    print()
    
    print("="*60)
    print("  ✅ Workflow Demonstration Complete!")
    print("="*60)
    print()
    print("SUMMARY:")
    print("  • User tried the app with 1 free generation")
    print("  • Experienced the quality of the product")
    print("  • Purchased Pro plan for ₹999/mo")
    print("  • Now has full access with 300 credits")
    print()

def main():
    """Main function"""
    print("\n" + "="*60)
    print("  🚀 ImageTo3D Pro - Trial System Demo")
    print("="*60)
    print()
    print("This demonstrates the complete user workflow:")
    print("  1. First launch → Trial offer")
    print("  2. Start trial → Generate 1 free model")
    print("  3. Trial used → License required")
    print("  4. Purchase → Full access unlocked")
    print()
    
    lm = get_license_manager()
    print(f"Current Status:")
    print(f"  Trial available: {lm.has_trial_available()}")
    print(f"  Trial remaining: {lm.get_trial_remaining()}")
    print()
    
    print("Options:")
    print("  1. Run workflow demonstration")
    print("  2. Reset trial (for testing)")
    print("  3. Exit")
    print()
    
    choice = input("Enter choice (1-3): ").strip()
    
    if choice == '1':
        simulate_workflow()
    elif choice == '2':
        lm.reset_trial()
        print("\n✅ Trial reset successfully!")
        print(f"   Trial available: {lm.has_trial_available()}")
        print(f"   Trial remaining: {lm.get_trial_remaining()}")
    else:
        print("\nGoodbye!")

if __name__ == "__main__":
    main()
