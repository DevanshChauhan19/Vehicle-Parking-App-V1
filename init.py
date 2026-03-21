from app import app, db
from werkzeug.security import generate_password_hash
from models import User, Role

with app.app_context():
    db.create_all()

    # Create roles if they don't exist
    roles = ['admin', 'user', 'collaborator']
    for role_name in roles:
        if not Role.query.filter_by(name=role_name).first():
            db.session.add(Role(name=role_name))

    db.session.commit()

    # Assign admin role to default admin
    admin_email = "admin@example.com"
    admin_password = "admin123"
    admin_role = Role.query.filter_by(name='admin').first()

    existing_admin = User.query.filter_by(email=admin_email).first()
    if not existing_admin:
        admin = User(
            name="Admin",
            email=admin_email,
            password_hash=generate_password_hash(admin_password),
            address="Default Admin Address",
            pincode=123456,
            role=admin_role
        )
        db.session.add(admin)
        print("Admin user created.")
    else:
        print("Admin user already exists.")

    db.session.commit()
