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
    phone_number = db.Column(db.String(20), nullable=True)  # WhatsApp number with country code e.g. +919876543210
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
    employee_name = db.Column(db.String(120), nullable=False)
    recipient_name = db.Column(db.String(120), nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow)

    # Status: draft, pending, approved, rejected
    status = db.Column(db.String(20), default='draft', nullable=False)

    # Creator (employee who created the expense)
    creator_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    # Signature file paths (legacy - for backwards compatibility)
    recipient_signature = db.Column(db.String(256), nullable=True)
    employee_signature = db.Column(db.String(256), nullable=True)
    senior_signature = db.Column(db.String(256), nullable=True)
    
    # Signature data stored as base64 (persistent storage)
    recipient_signature_data = db.Column(db.Text, nullable=True)
    employee_signature_data = db.Column(db.Text, nullable=True)
    senior_signature_data = db.Column(db.Text, nullable=True)
    
    # Attachment (bill/receipt image) stored as base64 (optional)
    attachment_data = db.Column(db.Text, nullable=True)
    attachment_filename = db.Column(db.String(256), nullable=True)

    # Approval information
    approved_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)
    rejection_reason = db.Column(db.String(500), nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Soft delete (recycle bin)
    is_deleted = db.Column(db.Boolean, default=False, nullable=False)
    deleted_at = db.Column(db.DateTime, nullable=True)
    deleted_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    # Relationships
    approved_by = db.relationship('User', foreign_keys=[approved_by_id])
    deleted_by = db.relationship('User', foreign_keys=[deleted_by_id])

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
            self.recipient_signature or self.recipient_signature_data,
            self.employee_signature or self.employee_signature_data,
            self.senior_signature or self.senior_signature_data
        ])

    def __repr__(self):
        return f'<Expense {self.id}: {self.purpose} - ${self.amount} ({self.status})>'


class CashTransaction(db.Model):
    """Cash transaction model for tracking money received and balance"""
    __tablename__ = 'cash_transactions'

    id = db.Column(db.Integer, primary_key=True)
    
    # Transaction type: 'received' for money in, 'expense' for money out
    transaction_type = db.Column(db.String(20), nullable=False)
    
    # Amount (positive for received, negative for expenses deducted)
    amount = db.Column(db.Float, nullable=False)
    
    # Description/source of the money
    description = db.Column(db.String(500), nullable=False)
    
    # Reference to expense if this is an expense deduction
    expense_id = db.Column(db.Integer, db.ForeignKey('expenses.id'), nullable=True)
    
    # Who recorded this transaction
    recorded_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Transaction date (user-selected date for when money was received)
    transaction_date = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    recorded_by = db.relationship('User', foreign_keys=[recorded_by_id])
    expense = db.relationship('Expense', foreign_keys=[expense_id])
    
    @staticmethod
    def get_current_balance():
        """Calculate current cash balance from all transactions"""
        result = db.session.query(db.func.sum(CashTransaction.amount)).scalar()
        return result if result else 0.0
    
    @staticmethod
    def get_total_received():
        """Get total money received"""
        result = db.session.query(db.func.sum(CashTransaction.amount)).filter(
            CashTransaction.transaction_type == 'received'
        ).scalar()
        return result if result else 0.0
    
    @staticmethod
    def get_total_expenses():
        """Get total expenses (absolute value)"""
        result = db.session.query(db.func.sum(CashTransaction.amount)).filter(
            CashTransaction.transaction_type == 'expense'
        ).scalar()
        return abs(result) if result else 0.0
    
    def __repr__(self):
        return f'<CashTransaction {self.id}: {self.transaction_type} ₹{self.amount}>'
