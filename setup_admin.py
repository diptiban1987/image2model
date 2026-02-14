"""Setup admin user for web app"""
from core.user_db import create_user, admin_exists

if __name__ == "__main__":
    if admin_exists():
        print("Admin user already exists!")
    else:
        create_user("admin", "admin123", is_admin=True)
        print("Admin user created!")
        print("Username: admin")
        print("Password: admin123")
