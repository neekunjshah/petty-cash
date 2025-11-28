"""
Database models for PettyCash NYSA
"""
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(UserMixin, db.Model):
    """User model with role-based access (employee/senior)"""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(120), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'employee' or 'senior'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    expenses_created = db.relationship('Expense', backref='creator', lazy=True,
                                      foreign_keys='Expense.creator_id')

    def set_password(self, password):
        """Hash and set password"""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Check password against hash"""
        return check_password_hash(self.password_hash, password)

    @property
    def is_senior(self):
        """Check if user is a senior"""
        return self.role == 'senior'

    @property
    def is_employee(self):
        """Check if user is an employee"""
        return self.role == 'employee'

    def __repr__(self):
        return f'<User {self.username} ({self.role})>'


class Expense(db.Model):
    """Expense model with triple signature support"""
    __tablename__ = 'expenses'

    id = db.Column(db.Integer, primary_key=True)

    # Basic expense information
    purpose = db.Column(db.String(500), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    recipient_name = db.Column(db.String(120), nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow)

    # Status: draft, pending, approved, rejected
    status = db.Column(db.String(20), default='draft', nullable=False)

    # Creator (employee who created the expense)
    creator_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    # Signature file paths (stored as PNG files)
    recipient_signature = db.Column(db.String(256), nullable=True)
    employee_signature = db.Column(db.String(256), nullable=True)
    senior_signature = db.Column(db.String(256), nullable=True)

    # Approval information
    approved_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)
    rejection_reason = db.Column(db.String(500), nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    approved_by = db.relationship('User', foreign_keys=[approved_by_id])

    @property
    def is_draft(self):
        return self.status == 'draft'

    @property
    def is_pending(self):
        return self.status == 'pending'

    @property
    def is_approved(self):
        return self.status == 'approved'

    @property
    def is_rejected(self):
        return self.status == 'rejected'

    @property
    def has_all_signatures(self):
        """Check if all three signatures are present"""
        return all([
            self.recipient_signature,
            self.employee_signature,
            self.senior_signature
        ])

    def __repr__(self):
        return f'<Expense {self.id}: {self.purpose} - ${self.amount} ({self.status})>'
