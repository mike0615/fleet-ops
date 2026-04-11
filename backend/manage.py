#!/usr/bin/env python
"""
CLI management tool for Maytag Admin Console (MAC).
Allows admin operations without web UI.
"""

import sys
import os
import getpass
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from flask import Flask
from backend.models import db, User, Role, init_db, create_default_roles
from backend.auth import create_user, validate_password


def create_app():
    """Create Flask app for CLI."""
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////var/lib/mac-ops/mac.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    return app


def cmd_create_admin(app):
    """Create initial admin user."""
    with app.app_context():
        init_db(app)
        create_default_roles(app)

        print("\n" + "="*50)
        print("MAC Admin User Setup")
        print("="*50 + "\n")

        # Check if admin already exists
        admin_user = User.query.filter_by(username='admin').first()
        if admin_user:
            print("✗ Admin user already exists")
            return

        # Get credentials
        username = input("Enter admin username [admin]: ").strip() or 'admin'

        # Check if username exists
        if User.query.filter_by(username=username).first():
            print(f"✗ User '{username}' already exists")
            return

        email = input(f"Enter email for {username}: ").strip()
        if not email:
            print("✗ Email is required")
            return

        while True:
            password = getpass.getpass("Enter password: ")
            valid, msg = validate_password(password)
            if not valid:
                print(f"✗ {msg}")
                continue

            password_confirm = getpass.getpass("Confirm password: ")
            if password != password_confirm:
                print("✗ Passwords do not match")
                continue

            break

        # Create user
        admin_role = Role.query.filter_by(name='admin').first()
        if not admin_role:
            print("✗ Admin role not found. Run 'mac-ops db init' first")
            return

        user, msg = create_user(username, email, password, auth_method='local', roles=['admin'])

        if user:
            print(f"\n✓ Admin user created successfully!")
            print(f"  Username: {username}")
            print(f"  Email: {email}")
        else:
            print(f"\n✗ Failed to create admin user: {msg}")


def cmd_create_user(app):
    """Create a new user."""
    with app.app_context():
        print("\n" + "="*50)
        print("Create New User")
        print("="*50 + "\n")

        username = input("Enter username: ").strip()
        if not username:
            print("✗ Username is required")
            return

        email = input("Enter email: ").strip()
        if not email:
            print("✗ Email is required")
            return

        print("\nPassword requirements:")
        print("  - At least 8 characters")
        print("  - Must contain uppercase, lowercase, and digits")

        while True:
            password = getpass.getpass("Enter password: ")
            valid, msg = validate_password(password)
            if not valid:
                print(f"✗ {msg}")
                continue
            break

        # Select role
        roles = Role.query.all()
        print("\nSelect role:")
        for i, role in enumerate(roles, 1):
            print(f"  {i}. {role.name} - {role.description}")

        while True:
            try:
                choice = int(input("Enter role number: "))
                if 1 <= choice <= len(roles):
                    role = roles[choice - 1]
                    break
                print("✗ Invalid choice")
            except ValueError:
                print("✗ Please enter a number")

        user, msg = create_user(username, email, password, auth_method='local', roles=[role.name])

        if user:
            print(f"\n✓ User created successfully!")
            print(f"  Username: {username}")
            print(f"  Email: {email}")
            print(f"  Role: {role.name}")
        else:
            print(f"\n✗ Failed to create user: {msg}")


def cmd_list_users(app):
    """List all users."""
    with app.app_context():
        users = User.query.all()

        if not users:
            print("No users found")
            return

        print("\n" + "="*80)
        print(f"{'ID':<5} {'Username':<20} {'Email':<30} {'Roles':<15} {'Enabled':<10}")
        print("="*80)

        for user in users:
            roles = ', '.join(r.name for r in user.roles) or 'none'
            status = '✓' if user.enabled else '✗'
            print(f"{user.id:<5} {user.username:<20} {user.email:<30} {roles:<15} {status:<10}")

        print("="*80)


def cmd_disable_user(app):
    """Disable a user."""
    with app.app_context():
        username = input("Enter username to disable: ").strip()
        user = User.query.filter_by(username=username).first()

        if not user:
            print(f"✗ User '{username}' not found")
            return

        user.enabled = False
        db.session.commit()
        print(f"✓ User '{username}' disabled")


def cmd_enable_user(app):
    """Enable a user."""
    with app.app_context():
        username = input("Enter username to enable: ").strip()
        user = User.query.filter_by(username=username).first()

        if not user:
            print(f"✗ User '{username}' not found")
            return

        user.enabled = True
        db.session.commit()
        print(f"✓ User '{username}' enabled")


def cmd_reset_password(app):
    """Reset user password."""
    with app.app_context():
        username = input("Enter username: ").strip()
        user = User.query.filter_by(username=username).first()

        if not user:
            print(f"✗ User '{username}' not found")
            return

        password = getpass.getpass("Enter new password: ")
        from backend.auth import validate_password
        valid, msg = validate_password(password)
        if not valid:
            print(f"✗ {msg}")
            return

        user.set_password(password)
        db.session.commit()
        print(f"✓ Password reset for user '{username}'")


def cmd_init_db(app):
    """Initialize database."""
    with app.app_context():
        print("Initializing database...")
        init_db(app)
        print("✓ Database initialized")

        print("Creating default roles...")
        create_default_roles(app)
        print("✓ Default roles created")


def main():
    """Main CLI entry point."""
    app = create_app()

    commands = {
        'create-admin': cmd_create_admin,
        'create-user': cmd_create_user,
        'list-users': cmd_list_users,
        'disable-user': cmd_disable_user,
        'enable-user': cmd_enable_user,
        'reset-password': cmd_reset_password,
        'init-db': cmd_init_db,
    }

    if len(sys.argv) < 2:
        print("Maytag Admin Console (MAC) Management Tool\n")
        print("Usage: python manage.py <command>\n")
        print("Commands:")
        for cmd in sorted(commands.keys()):
            print(f"  {cmd}")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd not in commands:
        print(f"✗ Unknown command: {cmd}")
        sys.exit(1)

    try:
        commands[cmd](app)
    except KeyboardInterrupt:
        print("\n✗ Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"✗ Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
