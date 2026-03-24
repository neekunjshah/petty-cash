"""
Main Flask application for PettyCash NYSA
Expense management system with triple digital signatures
"""
import os
from datetime import datetime
from flask import Flask, render_template, redirect, url_for, flash, request, make_response, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash
from flask_cors import CORS

from sqlalchemy.orm import joinedload
from config import Config
from models import db, User, Expense, CashTransaction
from whatsapp_service import notify_expense_submitted, notify_expense_approved, notify_expense_rejected

# Initialize Flask app
app = Flask(__name__)
app.config.from_object(Config)
CORS(app)

# Ensure upload folder exists (do this early, not just in __main__)
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize extensions
db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'

# Enable WAL mode for SQLite — better concurrent reads/writes, prevents data loss
if app.config['SQLALCHEMY_DATABASE_URI'].startswith('sqlite'):
    from sqlalchemy import event
    with app.app_context():
        @event.listens_for(db.engine, 'connect')
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute('PRAGMA journal_mode=WAL')
            cursor.execute('PRAGMA synchronous=NORMAL')
            cursor.close()


# Database session management
@app.teardown_appcontext
def shutdown_session(exception=None):
    """Clean up database session after each request"""
    if exception:
        db.session.rollback()
    db.session.remove()


@app.errorhandler(Exception)
def handle_exception(e):
    """Handle uncaught exceptions and rollback database session"""
    # Re-raise HTTP exceptions (404, 403, etc.) - these are intentional
    from werkzeug.exceptions import HTTPException
    if isinstance(e, HTTPException):
        return e
    
    # Handle database/application errors
    app.logger.error(f"Unhandled exception: {e}", exc_info=True)
    db.session.rollback()
    
    # Return error response
    if request.path.startswith('/api/'):
        return jsonify(error=str(e)), 500
    
    flash('An error occurred. Please try again.', 'danger')
    return redirect(url_for('dashboard'))


@login_manager.user_loader
def load_user(user_id):
    """Load user for Flask-Login"""
    try:
        return User.query.get(int(user_id))
    except Exception as e:
        app.logger.error(f"Error loading user {user_id}: {e}")
        db.session.rollback()
        return None


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
# SEO / CRAWL PREVENTION
# ============================================================================

@app.route('/robots.txt')
def robots():
    return "User-agent: *\nDisallow: /\n", 200, {'Content-Type': 'text/plain'}

@app.after_request
def add_noindex_header(response):
    response.headers['X-Robots-Tag'] = 'noindex, nofollow, noarchive, nosnippet'
    return response


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
        try:
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
        except Exception as e:
            app.logger.error(f"Login error: {e}")
            db.session.rollback()
            flash('An error occurred during login. Please try again.', 'danger')

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
    # Get cash balance info for all users
    current_balance = CashTransaction.get_current_balance()
    total_received = CashTransaction.get_total_received()
    total_expenses = CashTransaction.get_total_expenses()
    recent_transactions = CashTransaction.query.order_by(CashTransaction.created_at.desc()).limit(5).all()
    
    if current_user.is_senior:
        # Seniors see approval queue (exclude deleted)
        pending_expenses = Expense.query.options(joinedload(Expense.creator)).filter_by(status='pending', is_deleted=False).order_by(Expense.created_at.desc()).all()
        all_employees = User.query.filter_by(role='employee').order_by(User.full_name).all()
        all_seniors = User.query.filter_by(role='senior').order_by(User.full_name).all()
        # Count deleted expenses for recycle bin badge
        deleted_count = Expense.query.filter_by(is_deleted=True).count()
        return render_template('dashboard.html', 
                             pending_expenses=pending_expenses, 
                             all_employees=all_employees, 
                             all_seniors=all_seniors,
                             current_balance=current_balance,
                             total_received=total_received,
                             total_expenses=total_expenses,
                             recent_transactions=recent_transactions,
                             deleted_count=deleted_count)
    else:
        # Employees see their expenses (exclude deleted)
        my_expenses = Expense.query.options(joinedload(Expense.creator), joinedload(Expense.approved_by)).filter_by(creator_id=current_user.id, is_deleted=False).order_by(Expense.created_at.desc()).all()
        # Count their deleted expenses for recycle bin badge
        deleted_count = Expense.query.filter_by(creator_id=current_user.id, is_deleted=True).count()
        return render_template('dashboard.html', 
                             my_expenses=my_expenses,
                             current_balance=current_balance,
                             total_received=total_received,
                             total_expenses=total_expenses,
                             recent_transactions=recent_transactions,
                             deleted_count=deleted_count)


@app.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_profile():
    """Edit user profile (name, email, phone, password)"""
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip()
        phone_number = request.form.get('phone_number', '').strip()
        password = request.form.get('password', '').strip()
        password_confirm = request.form.get('password_confirm', '').strip()

        # Validate full_name
        if not full_name:
            flash('Full name cannot be empty', 'danger')
            return render_template('profile/edit.html')

        # Validate email if changed
        if email != current_user.email:
            if not email:
                flash('Email cannot be empty', 'danger')
                return render_template('profile/edit.html')
            
            if User.query.filter_by(email=email).first():
                flash('Email already in use', 'danger')
                return render_template('profile/edit.html')

        # Validate password if provided
        if password:
            if len(password) < 6:
                flash('Password must be at least 6 characters', 'danger')
                return render_template('profile/edit.html')
            
            if password != password_confirm:
                flash('Passwords do not match', 'danger')
                return render_template('profile/edit.html')
        
        # Validate phone number format (optional, but if provided should be valid)
        if phone_number:
            # Remove spaces and dashes
            phone_number = phone_number.replace(' ', '').replace('-', '')
            # Ensure it starts with +
            if not phone_number.startswith('+'):
                phone_number = '+' + phone_number

        # Update profile
        current_user.full_name = full_name
        current_user.email = email
        current_user.phone_number = phone_number if phone_number else None
        if password:
            current_user.set_password(password)

        db.session.commit()
        flash('Profile updated successfully', 'success')
        return redirect(url_for('dashboard'))

    return render_template('profile/edit.html')


# ============================================================================
# EXPENSE ROUTES
# ============================================================================

@app.route('/admin/employees/create', methods=['GET', 'POST'])
@login_required
def create_employee():
    """Create new employee (senior only)"""
    if not current_user.is_senior:
        flash('Only seniors can create employees', 'danger')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        full_name = request.form.get('full_name')
        email = request.form.get('email')
        username = request.form.get('username')
        password = request.form.get('password')

        # Validate
        if not all([full_name, email, username, password]):
            flash('All fields are required', 'danger')
            return render_template('admin/create_employee.html')

        # Check if username or email already exists
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'danger')
            return render_template('admin/create_employee.html')

        if User.query.filter_by(email=email).first():
            flash('Email already exists', 'danger')
            return render_template('admin/create_employee.html')

        # Create new employee
        employee = User(
            username=username,
            email=email,
            full_name=full_name,
            role='employee'
        )
        employee.set_password(password)

        db.session.add(employee)
        db.session.commit()

        flash(f'Employee {full_name} created successfully!', 'success')
        return redirect(url_for('dashboard'))

    return render_template('admin/create_employee.html')


@app.route('/admin/employees/<int:user_id>/rename', methods=['POST'])
@login_required
def rename_employee(user_id):
    """Rename employee (senior only)"""
    if not current_user.is_senior:
        flash('Only seniors can rename employees', 'danger')
        return redirect(url_for('dashboard'))

    user = User.query.get_or_404(user_id)
    
    if user.role != 'employee':
        flash('Only employees can be renamed this way', 'danger')
        return redirect(url_for('dashboard'))
    
    new_name = request.form.get('full_name', '').strip()
    if not new_name:
        flash('Name cannot be empty', 'danger')
        return redirect(url_for('dashboard'))
    
    old_name = user.full_name
    user.full_name = new_name
    db.session.commit()
    
    flash(f'Employee renamed from {old_name} to {new_name}', 'success')
    return redirect(url_for('dashboard'))


@app.route('/admin/employees/<int:user_id>/delete', methods=['POST'])
@login_required
def delete_employee(user_id):
    """Delete employee (senior only)"""
    if not current_user.is_senior:
        flash('Only seniors can delete employees', 'danger')
        return redirect(url_for('dashboard'))

    user = User.query.get_or_404(user_id)
    
    if user.role != 'employee':
        flash('Only employees can be deleted this way', 'danger')
        return redirect(url_for('dashboard'))
    
    full_name = user.full_name
    db.session.delete(user)
    db.session.commit()
    
    flash(f'Employee {full_name} deleted successfully', 'success')
    return redirect(url_for('dashboard'))


@app.route('/admin/seniors/<int:user_id>/rename', methods=['POST'])
@login_required
def rename_senior(user_id):
    """Rename senior (senior only)"""
    if not current_user.is_senior:
        flash('Only seniors can rename other seniors', 'danger')
        return redirect(url_for('dashboard'))

    user = User.query.get_or_404(user_id)
    
    if user.role != 'senior':
        flash('Only seniors can be renamed this way', 'danger')
        return redirect(url_for('dashboard'))
    
    new_name = request.form.get('full_name', '').strip()
    if not new_name:
        flash('Name cannot be empty', 'danger')
        return redirect(url_for('dashboard'))
    
    old_name = user.full_name
    user.full_name = new_name
    db.session.commit()
    
    flash(f'Senior renamed from {old_name} to {new_name}', 'success')
    return redirect(url_for('dashboard'))


@app.route('/admin/seniors/<int:user_id>/delete', methods=['POST'])
@login_required
def delete_senior(user_id):
    """Delete senior (senior only)"""
    if not current_user.is_senior:
        flash('Only seniors can delete other seniors', 'danger')
        return redirect(url_for('dashboard'))
    
    # Prevent deleting self
    if user_id == current_user.id:
        flash('You cannot delete yourself', 'danger')
        return redirect(url_for('dashboard'))

    user = User.query.get_or_404(user_id)
    
    if user.role != 'senior':
        flash('Only seniors can be deleted this way', 'danger')
        return redirect(url_for('dashboard'))
    
    full_name = user.full_name
    db.session.delete(user)
    db.session.commit()
    
    flash(f'Senior {full_name} deleted successfully', 'success')
    return redirect(url_for('dashboard'))


@app.route('/expenses')
@login_required
def expense_list():
    """List all expenses (filtered by status)"""
    status = request.args.get('status', 'all')

    base_query = Expense.query.options(joinedload(Expense.creator), joinedload(Expense.approved_by))
    if status == 'all':
        if current_user.is_senior:
            expenses = base_query.filter_by(is_deleted=False).order_by(Expense.created_at.desc()).all()
        else:
            expenses = base_query.filter_by(creator_id=current_user.id, is_deleted=False).order_by(Expense.created_at.desc()).all()
    else:
        if current_user.is_senior:
            expenses = base_query.filter_by(status=status, is_deleted=False).order_by(Expense.created_at.desc()).all()
        else:
            expenses = base_query.filter_by(creator_id=current_user.id, status=status, is_deleted=False).order_by(Expense.created_at.desc()).all()

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
        expense_date = request.form.get('expense_date')
        employee_id = request.form.get('employee_id')
        recipient_name = request.form.get('recipient_name')
        recipient_signature = request.form.get('recipient_signature')
        employee_signature = request.form.get('employee_signature')

        # Validate
        if not all([purpose, amount, expense_date, employee_id, recipient_name, recipient_signature, employee_signature]):
            flash('All fields and signatures are required', 'danger')
            employees = User.query.filter_by(role='employee').order_by(User.full_name).all()
            return render_template('expenses/create.html', current_date=datetime.now().strftime('%Y-%m-%d'), employees=employees)

        # Get employee name from employee_id
        employee = User.query.get(int(employee_id))
        if not employee or employee.role != 'employee':
            flash('Invalid employee selected', 'danger')
            employees = User.query.filter_by(role='employee').order_by(User.full_name).all()
            return render_template('expenses/create.html', current_date=datetime.now().strftime('%Y-%m-%d'), employees=employees)

        employee_name = employee.full_name

        # Handle optional attachment upload
        attachment_data = None
        attachment_filename = None
        attachment_file = request.files.get('attachment')
        if attachment_file and attachment_file.filename:
            import base64
            from werkzeug.utils import secure_filename
            
            # Check file size (5MB limit)
            attachment_file.seek(0, 2)  # Seek to end
            file_size = attachment_file.tell()
            attachment_file.seek(0)  # Reset to beginning
            
            if file_size > 5 * 1024 * 1024:
                flash('Attachment must be less than 5MB', 'danger')
                employees = User.query.filter_by(role='employee').order_by(User.full_name).all()
                return render_template('expenses/create.html', current_date=datetime.now().strftime('%Y-%m-%d'), employees=employees)
            
            # Read file content for validation
            file_content = attachment_file.read()
            attachment_file.seek(0)  # Reset for potential re-read
            
            # Validate file content by checking magic bytes (file headers)
            mime_type = None
            
            # Check for common image formats by magic bytes
            if file_content[:8] == b'\x89PNG\r\n\x1a\n':
                mime_type = 'image/png'
            elif file_content[:2] == b'\xff\xd8':
                mime_type = 'image/jpeg'
            elif file_content[:6] in (b'GIF87a', b'GIF89a'):
                mime_type = 'image/gif'
            elif file_content[:4] == b'RIFF' and file_content[8:12] == b'WEBP':
                mime_type = 'image/webp'
            elif file_content[:5] == b'%PDF-':
                mime_type = 'application/pdf'
            
            if not mime_type:
                flash('Invalid file type. Only images (JPG, PNG, GIF, WebP) and PDF files are allowed', 'danger')
                employees = User.query.filter_by(role='employee').order_by(User.full_name).all()
                return render_template('expenses/create.html', current_date=datetime.now().strftime('%Y-%m-%d'), employees=employees)
            
            # Sanitize filename
            filename = secure_filename(attachment_file.filename) or 'attachment'
            
            # Convert to base64
            base64_content = base64.b64encode(file_content).decode('utf-8')
            attachment_data = f"data:{mime_type};base64,{base64_content}"
            attachment_filename = filename

        # Save signatures as files (for backwards compatibility)
        recipient_sig_path = save_signature_image(recipient_signature, 'recipient')
        employee_sig_path = save_signature_image(employee_signature, 'employee')

        # Parse date
        expense_datetime = datetime.strptime(expense_date, '%Y-%m-%d')

        # Create expense with base64 data stored directly in database for persistence
        expense = Expense(
            purpose=purpose,
            amount=float(amount),
            date=expense_datetime,
            employee_name=employee_name,
            recipient_name=recipient_name,
            recipient_signature=recipient_sig_path,
            employee_signature=employee_sig_path,
            recipient_signature_data=recipient_signature,
            employee_signature_data=employee_signature,
            attachment_data=attachment_data,
            attachment_filename=attachment_filename,
            status='pending',  # Automatically submit for approval
            creator_id=current_user.id
        )

        try:
            db.session.add(expense)
            db.session.commit()
            expense_id = expense.id
            
            # Send WhatsApp notification to all seniors
            try:
                seniors = User.query.filter_by(role='senior').all()
                notify_expense_submitted(expense, seniors)
            except Exception as notif_error:
                app.logger.warning(f"WhatsApp notification failed: {notif_error}")
            
            db.session.remove()
            flash('Expense submitted for approval!', 'success')
            return redirect(url_for('expense_detail', expense_id=expense_id))
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Error creating expense: {e}")
            flash('Error submitting expense. Please try again.', 'danger')
            employees = User.query.filter_by(role='employee').order_by(User.full_name).all()
            return render_template('expenses/create.html', current_date=datetime.now().strftime('%Y-%m-%d'), employees=employees)

    employees = User.query.filter_by(role='employee').order_by(User.full_name).all()
    return render_template('expenses/create.html', current_date=datetime.now().strftime('%Y-%m-%d'), employees=employees)


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


@app.route('/expenses/<int:expense_id>/attachment')
@login_required
def download_attachment(expense_id):
    """Download expense attachment"""
    import base64
    from flask import Response
    
    expense = Expense.query.get_or_404(expense_id)

    # Authorization check
    if not current_user.is_senior and expense.creator_id != current_user.id:
        flash('You do not have permission to view this expense', 'danger')
        return redirect(url_for('dashboard'))
    
    if not expense.attachment_data:
        flash('No attachment found for this expense', 'warning')
        return redirect(url_for('expense_detail', expense_id=expense_id))
    
    # Parse data URL to extract mime type and content
    # Format: data:mime/type;base64,content
    try:
        header, base64_content = expense.attachment_data.split(',', 1)
        mime_type = header.split(':')[1].split(';')[0]
        file_content = base64.b64decode(base64_content)
        
        filename = expense.attachment_filename or 'attachment'
        
        return Response(
            file_content,
            mimetype=mime_type,
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"'
            }
        )
    except Exception as e:
        app.logger.error(f"Error downloading attachment: {e}")
        flash('Error downloading attachment', 'danger')
        return redirect(url_for('expense_detail', expense_id=expense_id))


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

    # Save senior signature (file for backwards compatibility)
    senior_sig_path = save_signature_image(senior_signature, 'senior')

    # Update expense with base64 data stored in database for persistence
    expense.status = 'approved'
    expense.senior_signature = senior_sig_path
    expense.senior_signature_data = senior_signature
    expense.approved_by_id = current_user.id
    expense.approved_at = datetime.utcnow()
    
    # Deduct amount from cash balance
    expense_transaction = CashTransaction(
        transaction_type='expense',
        amount=-expense.amount,  # Negative for expense
        description=f'Expense #{expense.id}: {expense.purpose[:50]}',
        expense_id=expense.id,
        recorded_by_id=current_user.id
    )
    db.session.add(expense_transaction)

    db.session.commit()
    
    # Send WhatsApp notification to employee
    try:
        notify_expense_approved(expense)
    except Exception as notif_error:
        app.logger.warning(f"WhatsApp notification failed: {notif_error}")

    flash(f'Expense #{expense_id} approved successfully! ₹{expense.amount:.2f} deducted from balance.', 'success')
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
    expense.approved_by_id = current_user.id

    db.session.commit()
    
    # Send WhatsApp notification to employee
    try:
        notify_expense_rejected(expense)
    except Exception as notif_error:
        app.logger.warning(f"WhatsApp notification failed: {notif_error}")

    flash(f'Expense #{expense_id} rejected', 'warning')
    return redirect(url_for('expense_detail', expense_id=expense_id))


@app.route('/expenses/<int:expense_id>/delete', methods=['POST'])
@login_required
def delete_expense(expense_id):
    """Soft delete expense - moves to recycle bin (creator or senior only)"""
    expense = Expense.query.get_or_404(expense_id)
    
    # Authorization check
    if not current_user.is_senior and expense.creator_id != current_user.id:
        flash('You do not have permission to delete this expense', 'danger')
        return redirect(url_for('dashboard'))
    
    expense_num = expense.id
    expense_amount = expense.amount
    was_approved = expense.status == 'approved'
    
    # If expense was approved, delete the cash transaction to return money to balance
    if was_approved:
        related_transaction = CashTransaction.query.filter_by(expense_id=expense_id).first()
        if related_transaction:
            # Simply delete the expense transaction (which was negative)
            # This automatically returns the money to the balance
            db.session.delete(related_transaction)
    
    # Soft delete the expense
    expense.is_deleted = True
    expense.deleted_at = datetime.now()
    expense.deleted_by_id = current_user.id
    
    db.session.commit()
    
    if was_approved:
        flash(f'Expense #{expense_num} moved to recycle bin. ₹{expense_amount:.2f} returned to cash balance.', 'success')
    else:
        flash(f'Expense #{expense_num} moved to recycle bin', 'success')
    return redirect(url_for('dashboard'))


# ============================================================================
# RECYCLE BIN ROUTES
# ============================================================================

@app.route('/recycle-bin')
@login_required
def recycle_bin():
    """View deleted expenses (recycle bin)"""
    if current_user.is_senior:
        # Seniors see all deleted expenses
        deleted_expenses = Expense.query.filter_by(is_deleted=True).order_by(Expense.deleted_at.desc()).all()
    else:
        # Employees see only their own deleted expenses
        deleted_expenses = Expense.query.filter_by(creator_id=current_user.id, is_deleted=True).order_by(Expense.deleted_at.desc()).all()
    
    return render_template('expenses/recycle_bin.html', deleted_expenses=deleted_expenses)


@app.route('/expenses/<int:expense_id>/restore', methods=['POST'])
@login_required
def restore_expense(expense_id):
    """Restore expense from recycle bin"""
    expense = Expense.query.get_or_404(expense_id)
    
    # Authorization check
    if not current_user.is_senior and expense.creator_id != current_user.id:
        flash('You do not have permission to restore this expense', 'danger')
        return redirect(url_for('recycle_bin'))
    
    if not expense.is_deleted:
        flash('This expense is not in the recycle bin', 'warning')
        return redirect(url_for('expense_detail', expense_id=expense_id))
    
    expense_num = expense.id
    expense_amount = expense.amount
    was_approved = expense.status == 'approved'
    
    # If expense was approved, re-create the cash deduction
    if was_approved:
        deduction = CashTransaction(
            transaction_type='expense',
            amount=-expense_amount,  # Negative to deduct
            description=f'Restored: Expense #{expense_num} - {expense.purpose}',
            expense_id=expense_id,
            recorded_by_id=current_user.id,
            transaction_date=datetime.now()
        )
        db.session.add(deduction)
    
    # Restore the expense
    expense.is_deleted = False
    expense.deleted_at = None
    expense.deleted_by_id = None
    
    db.session.commit()
    
    if was_approved:
        flash(f'Expense #{expense_num} restored. ₹{expense_amount:.2f} deducted from cash balance.', 'success')
    else:
        flash(f'Expense #{expense_num} restored successfully', 'success')
    return redirect(url_for('expense_detail', expense_id=expense_id))


@app.route('/expenses/<int:expense_id>/permanent-delete', methods=['POST'])
@login_required
def permanent_delete_expense(expense_id):
    """Permanently delete expense (seniors only)"""
    if not current_user.is_senior:
        flash('Only seniors can permanently delete expenses', 'danger')
        return redirect(url_for('recycle_bin'))
    
    expense = Expense.query.get_or_404(expense_id)
    
    if not expense.is_deleted:
        flash('Expense must be in recycle bin before permanent deletion', 'warning')
        return redirect(url_for('expense_detail', expense_id=expense_id))
    
    expense_num = expense.id
    
    # Delete any remaining cash transactions linked to this expense
    CashTransaction.query.filter_by(expense_id=expense_id).delete()
    
    # Permanently delete the expense
    db.session.delete(expense)
    db.session.commit()
    
    flash(f'Expense #{expense_num} permanently deleted', 'success')
    return redirect(url_for('recycle_bin'))


# ============================================================================
# SIGNATURE SERVING ROUTE
# ============================================================================

@app.route('/signatures/<filename>')
@login_required
def serve_signature(filename):
    """Serve signature images"""
    from flask import send_file
    sig_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    
    if not os.path.exists(sig_path):
        return "Signature not found", 404
    
    return send_file(sig_path, mimetype='image/png')


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

    # Get expenses based on role (exclude deleted) — eager load relationships
    if current_user.is_senior:
        expenses = Expense.query.options(joinedload(Expense.creator), joinedload(Expense.approved_by)).filter_by(status='approved', is_deleted=False).order_by(Expense.created_at.desc()).all()
    else:
        expenses = Expense.query.options(joinedload(Expense.creator), joinedload(Expense.approved_by)).filter_by(creator_id=current_user.id, is_deleted=False).order_by(Expense.created_at.desc()).all()

    # Create CSV
    si = StringIO()
    writer = csv.writer(si)

    # Header
    writer.writerow(['ID', 'Date', 'Purpose', 'Amount (₹)', 'Recipient', 'Status', 'Created By', 'Approved By', 'Approved Date'])

    # Data
    for expense in expenses:
        writer.writerow([
            expense.id,
            expense.created_at.strftime('%Y-%m-%d %H:%M'),
            expense.purpose,
            f'₹{expense.amount:.2f}',
            expense.recipient_name,
            expense.status.upper(),
            expense.creator.full_name,
            expense.approved_by.full_name if expense.approved_by else 'N/A',
            expense.approved_at.strftime('%Y-%m-%d %H:%M') if expense.approved_at else 'N/A'
        ])

    # Create response with UTF-8 BOM for Excel compatibility
    output = make_response('\ufeff' + si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=expenses.csv"
    output.headers["Content-type"] = "text/csv; charset=utf-8"

    return output


@app.route('/export/monthly-csv', methods=['GET', 'POST'])
@login_required
def export_monthly_csv():
    """Export monthly cash transactions to CSV with opening/closing balances"""

    if request.method == 'POST':
        month_year = request.form.get('month_year')
        if not month_year:
            flash('Please select a month', 'danger')
            return render_template('export/monthly_csv.html', current_date=datetime.now())

        try:
            year, month = map(int, month_year.split('-'))
        except (ValueError, AttributeError):
            flash('Invalid month format', 'danger')
            return render_template('export/monthly_csv.html', current_date=datetime.now())

        from datetime import timedelta
        first_day = datetime(year, month, 1)
        if month == 12:
            last_day = datetime(year + 1, 1, 1) - timedelta(days=1)
        else:
            last_day = datetime(year, month + 1, 1) - timedelta(days=1)
        last_day_end = last_day.replace(hour=23, minute=59, second=59)

        # Calculate opening balance (sum of all transactions before this month)
        opening_balance_result = db.session.query(db.func.sum(CashTransaction.amount)).filter(
            CashTransaction.created_at < first_day
        ).scalar()
        opening_balance = opening_balance_result if opening_balance_result else 0.0

        # Get all transactions for the month (both received and expense) — eager load linked expense+creator
        transactions = CashTransaction.query.options(
            joinedload(CashTransaction.expense).joinedload(Expense.creator)
        ).filter(
            CashTransaction.created_at >= first_day,
            CashTransaction.created_at <= last_day_end
        ).order_by(CashTransaction.created_at).all()

        import csv
        from io import StringIO
        si = StringIO()
        writer = csv.writer(si)
        
        # Header row with month info
        month_name = first_day.strftime('%B %Y')
        writer.writerow([f'Cash Transactions Report - {month_name}'])
        writer.writerow([])
        
        # Opening balance row
        writer.writerow(['Opening Balance', '', '', f'₹{opening_balance:.2f}'])
        writer.writerow([])
        
        # Column headers
        writer.writerow(['Date', 'Type', 'Description', 'Recipient Name', 'Employee Name', 'Amount (₹)', 'Running Balance (₹)'])
        
        # Calculate running balance starting from opening balance
        running_balance = opening_balance
        total_received = 0.0
        total_expenses = 0.0
        
        for txn in transactions:
            running_balance += txn.amount
            txn_type = 'Received' if txn.transaction_type == 'received' else 'Expense'
            
            # Track totals
            recipient_name = ''
            employee_name = ''
            
            if txn.transaction_type == 'received':
                total_received += txn.amount
                # For received transactions, these fields are not applicable
                recipient_name = '-'
                employee_name = '-'
            else:
                total_expenses += abs(txn.amount)
                # For expense: get recipient and employee from linked expense (eager loaded)
                if txn.expense:
                    recipient_name = txn.expense.recipient_name
                    employee_name = txn.expense.creator.full_name if txn.expense.creator else 'N/A'
                else:
                    recipient_name = 'N/A'
                    employee_name = 'N/A'
            
            writer.writerow([
                txn.created_at.strftime('%Y-%m-%d'),
                txn_type,
                txn.description,
                recipient_name,
                employee_name,
                f'₹{txn.amount:.2f}',
                f'₹{running_balance:.2f}'
            ])
        
        writer.writerow([])
        
        # Summary section
        closing_balance = running_balance
        writer.writerow(['Summary'])
        writer.writerow(['Total Received', '', '', f'₹{total_received:.2f}'])
        writer.writerow(['Total Expenses', '', '', f'-₹{total_expenses:.2f}'])
        writer.writerow(['Closing Balance', '', '', f'₹{closing_balance:.2f}'])

        output = make_response('\ufeff' + si.getvalue())
        output.headers["Content-Disposition"] = f"attachment; filename=cash_report_{year}_{month:02d}.csv"
        output.headers["Content-type"] = "text/csv; charset=utf-8"
        return output

    current_date = datetime.now()
    return render_template('export/monthly_csv.html', current_date=current_date)


@app.route('/export/monthly-pdf', methods=['GET', 'POST'])
@login_required
def export_monthly_pdf():
    """Export all expenses for a month to PDF (all users can access)"""

    if request.method == 'POST':
        month_year = request.form.get('month_year')
        current_date = datetime.now()
        
        if not month_year:
            flash('Please select a month', 'danger')
            return render_template('export/monthly_pdf.html', current_date=current_date)

        # Parse month_year (format: YYYY-MM)
        try:
            year, month = map(int, month_year.split('-'))
        except (ValueError, AttributeError):
            flash('Invalid month format', 'danger')
            return render_template('export/monthly_pdf.html', current_date=current_date)

        # Get first and last day of the month
        from datetime import timedelta
        first_day = datetime(year, month, 1)
        if month == 12:
            last_day = datetime(year + 1, 1, 1) - timedelta(days=1)
        else:
            last_day = datetime(year, month + 1, 1) - timedelta(days=1)
        # Include end of last day (23:59:59)
        last_day_end = last_day.replace(hour=23, minute=59, second=59)

        # Get all approved expenses for the month (exclude deleted) — eager load relationships
        expenses = Expense.query.options(
            joinedload(Expense.creator), joinedload(Expense.approved_by)
        ).filter(
            Expense.status == 'approved',
            Expense.is_deleted == False,
            Expense.approved_at >= first_day,
            Expense.approved_at <= last_day_end
        ).order_by(Expense.approved_at).all()

        if not expenses:
            flash(f'No approved expenses found for {first_day.strftime("%B %Y")}', 'info')
            return render_template('export/monthly_pdf.html', current_date=datetime.now())

        # Generate PDF
        from reportlab.lib.pagesizes import letter
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, PageBreak
        from reportlab.lib.styles import getSampleStyleSheet
        from io import BytesIO

        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        elements = []
        styles = getSampleStyleSheet()

        # Company logo at the top
        logo_path = os.path.join(app.root_path, 'static', 'images', 'logo.png')
        if os.path.exists(logo_path):
            try:
                logo = Image(logo_path, width=56, height=56)
                elements.append(logo)
                elements.append(Spacer(1, 10))
            except Exception as e:
                app.logger.warning(f"Could not load logo for PDF: {e}")

        # Title
        title_text = f"MONTHLY EXPENSE REPORT - {first_day.strftime('%B %Y')}"
        elements.append(Paragraph(title_text, styles['Title']))
        elements.append(Spacer(1, 20))

        # Summary table
        total_amount = sum(expense.amount for expense in expenses)
        summary_data = [
            ['Total Expenses:', f'₹{total_amount:.2f}'],
            ['Number of Expenses:', str(len(expenses))],
            ['Report Date:', datetime.now().strftime('%Y-%m-%d')],
        ]
        summary_table = Table(summary_data, colWidths=[200, 300])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.lightblue),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('PADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        elements.append(summary_table)
        elements.append(Spacer(1, 20))

        # Add each expense as a separate section
        for idx, expense in enumerate(expenses, 1):
            # Page break between expenses (except after the first)
            if idx > 1:
                elements.append(PageBreak())

            # Expense number
            elements.append(Paragraph(f"Expense #{expense.id}", styles['Heading1']))
            elements.append(Spacer(1, 12))

            # Expense details
            data = [
                ['Date:', expense.approved_at.strftime('%Y-%m-%d %H:%M')],
                ['Purpose:', expense.purpose],
                ['Amount:', f'₹{expense.amount:.2f}'],
                ['Recipient:', expense.recipient_name],
                ['Employee:', expense.creator.full_name],
                ['Approved By:', expense.approved_by.full_name if expense.approved_by else 'N/A'],
            ]

            table = Table(data, colWidths=[150, 350])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('PADDING', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            elements.append(table)
            elements.append(Spacer(1, 16))

            # Signatures
            elements.append(Paragraph("Signatures:", styles['Heading2']))
            elements.append(Spacer(1, 8))

            # Helper function to get signature image from base64 data or file
            def get_sig_image(signature_data, signature_file, width=100, height=50):
                import base64
                
                # First try base64 data from database
                if signature_data:
                    try:
                        # Remove data URL prefix if present
                        if ',' in signature_data:
                            base64_str = signature_data.split(',')[1]
                        else:
                            base64_str = signature_data
                        
                        image_bytes = base64.b64decode(base64_str)
                        img_buffer = BytesIO(image_bytes)
                        return Image(img_buffer, width=width, height=height)
                    except Exception as e:
                        app.logger.warning(f"Error loading signature from database: {e}")
                
                # Fall back to file if database data not available
                if signature_file:
                    sig_path = os.path.join(app.config['UPLOAD_FOLDER'], signature_file)
                    if os.path.exists(sig_path):
                        try:
                            return Image(sig_path, width=width, height=height)
                        except Exception as e:
                            app.logger.warning(f"Error loading signature file: {e}")
                
                return None

            sig_data = []
            try:
                # Recipient signature
                recipient_img = get_sig_image(expense.recipient_signature_data, expense.recipient_signature)
                if recipient_img:
                    sig_data.append(['Recipient:', recipient_img])
                    sig_data.append(['', Paragraph(expense.recipient_name, styles['Normal'])])

                # Employee signature
                employee_img = get_sig_image(expense.employee_signature_data, expense.employee_signature)
                if employee_img:
                    sig_data.append(['Employee:', employee_img])
                    sig_data.append(['', Paragraph(expense.creator.full_name, styles['Normal'])])

                # Senior signature
                senior_img = get_sig_image(expense.senior_signature_data, expense.senior_signature)
                if senior_img:
                    sig_data.append(['Senior:', senior_img])
                    sig_data.append(['', Paragraph(expense.approved_by.full_name if expense.approved_by else 'N/A', styles['Normal'])])
            except Exception as e:
                app.logger.error(f"Error processing signatures for expense {expense.id}: {e}")

            if sig_data:
                sig_table = Table(sig_data, colWidths=[80, 350])
                sig_table.setStyle(TableStyle([
                    ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, -1), 9),
                    ('PADDING', (0, 0), (-1, -1), 4),
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ]))
                elements.append(sig_table)

        # Build PDF
        doc.build(elements)

        # Create response
        pdf = buffer.getvalue()
        buffer.close()

        response = make_response(pdf)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'attachment; filename=expenses_{first_day.strftime("%Y_%m")}.pdf'

        return response

    current_date = datetime.now()
    return render_template('export/monthly_pdf.html', current_date=current_date)


@app.route('/export/pdf/<int:expense_id>')
@login_required
def export_pdf(expense_id):
    """Export single expense to PDF"""
    expense = Expense.query.options(
        joinedload(Expense.creator), joinedload(Expense.approved_by)
    ).get_or_404(expense_id)

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

    # Company logo at the top
    logo_path = os.path.join(app.root_path, 'static', 'images', 'logo.png')
    if os.path.exists(logo_path):
        try:
            logo = Image(logo_path, width=56, height=56)
            elements.append(logo)
            elements.append(Spacer(1, 10))
        except Exception as e:
            app.logger.warning(f"Could not load logo for PDF: {e}")

    # Title
    elements.append(Paragraph("EXPENSE VOUCHER", styles['Title']))
    elements.append(Spacer(1, 12))

    # Expense details
    data = [
        ['Expense ID:', f'#{expense.id}'],
        ['Date:', expense.created_at.strftime('%Y-%m-%d %H:%M')],
        ['Status:', expense.status.upper()],
        ['Purpose:', expense.purpose],
        ['Amount:', f'₹{expense.amount:.2f}'],
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

    # Helper function to get signature image from base64 data or file
    def get_signature_image(signature_data, signature_file):
        import base64
        from PIL import Image as PILImage
        
        # First try base64 data from database
        if signature_data:
            try:
                # Remove data URL prefix if present
                if ',' in signature_data:
                    base64_str = signature_data.split(',')[1]
                else:
                    base64_str = signature_data
                
                image_bytes = base64.b64decode(base64_str)
                img_buffer = BytesIO(image_bytes)
                return Image(img_buffer, width=150, height=75)
            except Exception as e:
                app.logger.error(f"Error loading signature from database: {e}")
        
        # Fall back to file if database data not available
        if signature_file:
            sig_path = os.path.join(app.config['UPLOAD_FOLDER'], signature_file)
            if os.path.exists(sig_path):
                return Image(sig_path, width=150, height=75)
        
        return None

    # Create table with signature images
    sig_data = []

    recipient_img = get_signature_image(expense.recipient_signature_data, expense.recipient_signature)
    if recipient_img:
        sig_data.append(['Recipient:', recipient_img])
        sig_data.append(['', Paragraph(expense.recipient_name, styles['Normal'])])

    employee_img = get_signature_image(expense.employee_signature_data, expense.employee_signature)
    if employee_img:
        sig_data.append(['Employee:', employee_img])
        sig_data.append(['', Paragraph(expense.creator.full_name if expense.creator else expense.employee_name, styles['Normal'])])

    senior_img = get_signature_image(expense.senior_signature_data, expense.senior_signature)
    if senior_img:
        sig_data.append(['Senior:', senior_img])
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
# CASH TRANSACTION ENDPOINTS
# ============================================================================

@app.route('/cash/add', methods=['GET', 'POST'])
@login_required
def add_cash():
    """Add money received to the cash balance (all users can access)"""
    
    if request.method == 'POST':
        try:
            amount = float(request.form.get('amount', 0))
            description = request.form.get('description', '').strip()
            transaction_date_str = request.form.get('transaction_date', '')
            
            if amount <= 0:
                flash('Amount must be greater than zero', 'danger')
                return redirect(url_for('add_cash'))
            
            if not description:
                flash('Please provide a description/source for the money', 'danger')
                return redirect(url_for('add_cash'))
            
            # Parse transaction date
            if transaction_date_str:
                transaction_date = datetime.strptime(transaction_date_str, '%Y-%m-%d')
            else:
                transaction_date = datetime.utcnow()
            
            # Create cash transaction
            transaction = CashTransaction(
                transaction_type='received',
                amount=amount,
                description=description,
                recorded_by_id=current_user.id,
                transaction_date=transaction_date
            )
            db.session.add(transaction)
            db.session.commit()
            
            flash(f'Successfully added ₹{amount:.2f} to cash balance', 'success')
            return redirect(url_for('dashboard'))
            
        except ValueError:
            flash('Invalid amount entered', 'danger')
            return redirect(url_for('add_cash'))
    
    current_balance = CashTransaction.get_current_balance()
    current_date = datetime.now().strftime('%Y-%m-%d')
    return render_template('cash/add.html', current_balance=current_balance, current_date=current_date)


@app.route('/cash/history')
@login_required
def cash_history():
    """View all cash transactions"""
    transactions = CashTransaction.query.order_by(CashTransaction.created_at.desc()).all()
    current_balance = CashTransaction.get_current_balance()
    total_received = CashTransaction.get_total_received()
    total_expenses = CashTransaction.get_total_expenses()
    
    return render_template('cash/history.html',
                         transactions=transactions,
                         current_balance=current_balance,
                         total_received=total_received,
                         total_expenses=total_expenses)


@app.route('/cash/delete/<int:transaction_id>', methods=['POST'])
@login_required
def delete_cash_transaction(transaction_id):
    """Delete a cash received transaction (senior only)"""
    # Only seniors can delete cash transactions
    if not current_user.is_senior:
        flash('Only seniors can delete cash transactions', 'danger')
        return redirect(url_for('cash_history'))
    
    transaction = CashTransaction.query.get_or_404(transaction_id)
    
    # Only allow deletion of 'received' type transactions (not expense deductions)
    if transaction.transaction_type != 'received':
        flash('Cannot delete expense deductions. Delete the expense instead.', 'danger')
        return redirect(url_for('cash_history'))
    
    amount = transaction.amount
    db.session.delete(transaction)
    db.session.commit()
    
    flash(f'Cash entry of ₹{amount:.2f} deleted successfully', 'success')
    return redirect(url_for('cash_history'))


# ============================================================================
# NOTIFICATION ENDPOINTS
# ============================================================================

@app.route('/api/notify-seniors', methods=['POST'])
@login_required
def notify_seniors():
    """Send notification to all seniors about pending approval"""
    if not current_user.is_senior and not current_user.is_employee:
        return jsonify({'error': 'Unauthorized'}), 403
    
    data = request.get_json() or {}
    message = data.get('message', 'New expense awaiting approval')
    
    # Get all seniors
    seniors = User.query.filter_by(role='senior').all()
    
    return jsonify({
        'status': 'success',
        'message': 'Notification ready to send',
        'seniors_count': len(seniors)
    })


@app.route('/api/check-notifications', methods=['GET'])
@login_required
def check_notifications():
    """Check for pending expenses (for seniors)"""
    if not current_user.is_senior:
        return jsonify({'error': 'Unauthorized'}), 403
    
    pending_expenses = Expense.query.filter_by(status='pending', is_deleted=False).count()
    
    return jsonify({
        'pending_count': pending_expenses,
        'has_pending': pending_expenses > 0
    })


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

# Initialize database (runs for both gunicorn and direct execution)
try:
    init_db()
except Exception as e:
    print(f"Database initialization warning: {e}")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('FLASK_DEBUG', 'False') == 'True'
    app.run(debug=debug_mode, host='0.0.0.0', port=port)
