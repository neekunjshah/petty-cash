"""
Main Flask application for PettyCash NYSA
Expense management system with triple digital signatures
"""
import os
from flask import Flask, render_template, redirect, url_for, flash, request
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash

from config import Config
from models import db, User, Expense

# Initialize Flask app
app = Flask(__name__)
app.config.from_object(Config)

# Initialize extensions
db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'


@login_manager.user_loader
def load_user(user_id):
    """Load user for Flask-Login"""
    return User.query.get(int(user_id))


def init_db():
    """Initialize database with seed data"""
    with app.app_context():
        # Create tables
        db.create_all()

        # Check if users already exist
        if User.query.count() == 0:
            # Create employee user
            employee = User(
                username='employee',
                email='employee@example.com',
                full_name='John Employee',
                role='employee'
            )
            employee.set_password('password123')

            # Create senior user
            senior = User(
                username='senior',
                email='senior@example.com',
                full_name='Jane Senior',
                role='senior'
            )
            senior.set_password('password123')

            db.session.add(employee)
            db.session.add(senior)
            db.session.commit()

            print("✅ Database initialized with seed data")
            print("Employee Login: employee@example.com / password123")
            print("Senior Login: senior@example.com / password123")
        else:
            print("✅ Database already initialized")


# ============================================================================
# AUTHENTICATION ROUTES
# ============================================================================

@app.route('/')
def index():
    """Redirect to dashboard if authenticated, otherwise login"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            login_user(user, remember=True)
            flash(f'Welcome back, {user.full_name}!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password', 'danger')

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    """Logout current user"""
    logout_user()
    flash('You have been logged out', 'info')
    return redirect(url_for('login'))


# ============================================================================
# DASHBOARD
# ============================================================================

@app.route('/dashboard')
@login_required
def dashboard():
    """Main dashboard - shows different content based on role"""
    if current_user.is_senior:
        # Seniors see approval queue
        pending_expenses = Expense.query.filter_by(status='pending').order_by(Expense.created_at.desc()).all()
        return render_template('dashboard.html', pending_expenses=pending_expenses)
    else:
        # Employees see their expenses
        my_expenses = Expense.query.filter_by(creator_id=current_user.id).order_by(Expense.created_at.desc()).all()
        return render_template('dashboard.html', my_expenses=my_expenses)


# ============================================================================
# EXPENSE ROUTES
# ============================================================================

@app.route('/expenses')
@login_required
def expense_list():
    """List all expenses (filtered by status)"""
    status = request.args.get('status', 'all')

    if status == 'all':
        if current_user.is_senior:
            expenses = Expense.query.order_by(Expense.created_at.desc()).all()
        else:
            expenses = Expense.query.filter_by(creator_id=current_user.id).order_by(Expense.created_at.desc()).all()
    else:
        if current_user.is_senior:
            expenses = Expense.query.filter_by(status=status).order_by(Expense.created_at.desc()).all()
        else:
            expenses = Expense.query.filter_by(creator_id=current_user.id, status=status).order_by(Expense.created_at.desc()).all()

    return render_template('expenses/list.html', expenses=expenses, status=status)


@app.route('/expenses/create', methods=['GET', 'POST'])
@login_required
def expense_create():
    """Create new expense"""
    if current_user.is_senior:
        flash('Seniors cannot create expenses', 'warning')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        purpose = request.form.get('purpose')
        amount = request.form.get('amount')
        recipient_name = request.form.get('recipient_name')
        recipient_signature = request.form.get('recipient_signature')
        employee_signature = request.form.get('employee_signature')

        # Validate
        if not all([purpose, amount, recipient_name, recipient_signature, employee_signature]):
            flash('All fields and signatures are required', 'danger')
            return render_template('expenses/create.html')

        # Save signatures as files
        recipient_sig_path = save_signature_image(recipient_signature, 'recipient')
        employee_sig_path = save_signature_image(employee_signature, 'employee')

        # Create expense
        expense = Expense(
            purpose=purpose,
            amount=float(amount),
            recipient_name=recipient_name,
            recipient_signature=recipient_sig_path,
            employee_signature=employee_sig_path,
            status='pending',  # Automatically submit for approval
            creator_id=current_user.id
        )

        db.session.add(expense)
        db.session.commit()

        flash('Expense submitted for approval!', 'success')
        return redirect(url_for('expense_detail', expense_id=expense.id))

    return render_template('expenses/create.html')


@app.route('/expenses/<int:expense_id>')
@login_required
def expense_detail(expense_id):
    """View expense details"""
    expense = Expense.query.get_or_404(expense_id)

    # Authorization check
    if not current_user.is_senior and expense.creator_id != current_user.id:
        flash('You do not have permission to view this expense', 'danger')
        return redirect(url_for('dashboard'))

    return render_template('expenses/detail.html', expense=expense)


@app.route('/expenses/<int:expense_id>/approve', methods=['POST'])
@login_required
def expense_approve(expense_id):
    """Approve expense (senior only)"""
    if not current_user.is_senior:
        flash('Only seniors can approve expenses', 'danger')
        return redirect(url_for('dashboard'))

    expense = Expense.query.get_or_404(expense_id)

    if expense.status != 'pending':
        flash('Only pending expenses can be approved', 'warning')
        return redirect(url_for('expense_detail', expense_id=expense_id))

    # Get senior signature
    senior_signature = request.form.get('senior_signature')
    if not senior_signature:
        flash('Senior signature is required', 'danger')
        return redirect(url_for('expense_detail', expense_id=expense_id))

    # Save senior signature
    senior_sig_path = save_signature_image(senior_signature, 'senior')

    # Update expense
    from datetime import datetime
    expense.status = 'approved'
    expense.senior_signature = senior_sig_path
    expense.approved_by_id = current_user.id
    expense.approved_at = datetime.utcnow()

    db.session.commit()

    flash(f'Expense #{expense_id} approved successfully!', 'success')
    return redirect(url_for('expense_detail', expense_id=expense_id))


@app.route('/expenses/<int:expense_id>/reject', methods=['POST'])
@login_required
def expense_reject(expense_id):
    """Reject expense (senior only)"""
    if not current_user.is_senior:
        flash('Only seniors can reject expenses', 'danger')
        return redirect(url_for('dashboard'))

    expense = Expense.query.get_or_404(expense_id)

    if expense.status != 'pending':
        flash('Only pending expenses can be rejected', 'warning')
        return redirect(url_for('expense_detail', expense_id=expense_id))

    reason = request.form.get('rejection_reason')
    if not reason:
        flash('Rejection reason is required', 'danger')
        return redirect(url_for('expense_detail', expense_id=expense_id))

    expense.status = 'rejected'
    expense.rejection_reason = reason

    db.session.commit()

    flash(f'Expense #{expense_id} rejected', 'warning')
    return redirect(url_for('expense_detail', expense_id=expense_id))


# ============================================================================
# EXPORT ROUTES
# ============================================================================

@app.route('/export/csv')
@login_required
def export_csv():
    """Export expenses to CSV"""
    import csv
    from io import StringIO
    from flask import make_response

    # Get expenses based on role
    if current_user.is_senior:
        expenses = Expense.query.filter_by(status='approved').order_by(Expense.created_at.desc()).all()
    else:
        expenses = Expense.query.filter_by(creator_id=current_user.id).order_by(Expense.created_at.desc()).all()

    # Create CSV
    si = StringIO()
    writer = csv.writer(si)

    # Header
    writer.writerow(['ID', 'Date', 'Purpose', 'Amount', 'Recipient', 'Status', 'Created By', 'Approved By', 'Approved Date'])

    # Data
    for expense in expenses:
        writer.writerow([
            expense.id,
            expense.created_at.strftime('%Y-%m-%d %H:%M'),
            expense.purpose,
            f'${expense.amount:.2f}',
            expense.recipient_name,
            expense.status.upper(),
            expense.creator.full_name,
            expense.approved_by.full_name if expense.approved_by else 'N/A',
            expense.approved_at.strftime('%Y-%m-%d %H:%M') if expense.approved_at else 'N/A'
        ])

    # Create response
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=expenses.csv"
    output.headers["Content-type"] = "text/csv"

    return output


@app.route('/export/pdf/<int:expense_id>')
@login_required
def export_pdf(expense_id):
    """Export single expense to PDF"""
    expense = Expense.query.get_or_404(expense_id)

    # Authorization check
    if not current_user.is_senior and expense.creator_id != current_user.id:
        flash('You do not have permission to export this expense', 'danger')
        return redirect(url_for('dashboard'))

    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
    from reportlab.lib.styles import getSampleStyleSheet
    from io import BytesIO
    from flask import make_response

    # Create PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()

    # Title
    elements.append(Paragraph("EXPENSE VOUCHER", styles['Title']))
    elements.append(Spacer(1, 12))

    # Expense details
    data = [
        ['Expense ID:', f'#{expense.id}'],
        ['Date:', expense.created_at.strftime('%Y-%m-%d %H:%M')],
        ['Status:', expense.status.upper()],
        ['Purpose:', expense.purpose],
        ['Amount:', f'${expense.amount:.2f}'],
        ['Recipient:', expense.recipient_name],
        ['Created By:', expense.creator.full_name],
    ]

    if expense.approved_by:
        data.append(['Approved By:', expense.approved_by.full_name])
        data.append(['Approved Date:', expense.approved_at.strftime('%Y-%m-%d %H:%M')])

    table = Table(data, colWidths=[150, 350])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('PADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    elements.append(table)
    elements.append(Spacer(1, 20))

    # Signatures with actual images
    elements.append(Paragraph("Signatures:", styles['Heading2']))
    elements.append(Spacer(1, 12))

    # Create table with signature images
    sig_data = []
    sig_images = []

    if expense.recipient_signature:
        sig_path = os.path.join(app.config['UPLOAD_FOLDER'], expense.recipient_signature)
        if os.path.exists(sig_path):
            sig_img = Image(sig_path, width=150, height=75)
            sig_data.append(['Recipient:', sig_img])
            sig_data.append(['', Paragraph(expense.recipient_name, styles['Normal'])])

    if expense.employee_signature:
        sig_path = os.path.join(app.config['UPLOAD_FOLDER'], expense.employee_signature)
        if os.path.exists(sig_path):
            sig_img = Image(sig_path, width=150, height=75)
            sig_data.append(['Employee:', sig_img])
            sig_data.append(['', Paragraph(expense.creator.full_name, styles['Normal'])])

    if expense.senior_signature:
        sig_path = os.path.join(app.config['UPLOAD_FOLDER'], expense.senior_signature)
        if os.path.exists(sig_path):
            sig_img = Image(sig_path, width=150, height=75)
            sig_data.append(['Senior:', sig_img])
            sig_data.append(['', Paragraph(expense.approved_by.full_name if expense.approved_by else 'N/A', styles['Normal'])])

    if sig_data:
        sig_table = Table(sig_data, colWidths=[100, 400])
        sig_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('PADDING', (0, 0), (-1, -1), 8),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BOX', (0, 0), (-1, -1), 1, colors.black),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        elements.append(sig_table)

    # Build PDF
    doc.build(elements)

    # Create response
    pdf = buffer.getvalue()
    buffer.close()

    response = make_response(pdf)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename=expense_{expense_id}.pdf'

    return response


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def save_signature_image(base64_data, sig_type):
    """Save base64 signature image to file"""
    import base64
    import uuid
    from PIL import Image
    from io import BytesIO

    # Remove data URL prefix
    if ',' in base64_data:
        base64_data = base64_data.split(',')[1]

    # Decode base64
    image_data = base64.b64decode(base64_data)

    # Generate unique filename
    filename = f'{sig_type}_{uuid.uuid4().hex}.png'
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)

    # Save image
    image = Image.open(BytesIO(image_data))
    image.save(filepath, 'PNG')

    return filename


# ============================================================================
# RUN APPLICATION
# ============================================================================

if __name__ == '__main__':
    # Ensure upload folder exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    # Ensure instance folder exists for SQLite database
    instance_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'instance')
    os.makedirs(instance_path, exist_ok=True)

    # Initialize database
    init_db()

    # Run app
    print("\n🚀 Starting PettyCash NYSA Web App")
    print("📍 Access at: http://127.0.0.1:8000")
    print("\n")
    app.run(debug=True, host='0.0.0.0', port=8000)
