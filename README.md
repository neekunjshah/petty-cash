# PettyCash NYSA - Web Application

A complete expense management system with triple digital signatures, role-based access, and PDF/CSV export.

## Features

✅ **Authentication System**
- Secure login with password hashing
- Role-based access (Employee vs Senior)

✅ **Expense Management**
- Create expenses with purpose, amount, and recipient
- Triple digital signature capture (Recipient, Employee, Senior)
- Status tracking (Draft, Pending, Approved, Rejected)

✅ **Approval Workflow**
- Seniors review and approve/reject expenses
- Digital signature required for approval
- Rejection with reason tracking

✅ **Export Functionality**
- CSV export of all expenses
- PDF export of individual expense vouchers
- Includes all signatures and details

✅ **User Interface**
- Clean, responsive Bootstrap 5 design
- HTML5 Canvas for signature capture
- Mobile-friendly touch support

## Tech Stack

- **Backend:** Flask 3.0
- **Database:** SQLite with SQLAlchemy ORM
- **Auth:** Flask-Login
- **Frontend:** Bootstrap 5 + vanilla JavaScript
- **Signatures:** HTML5 Canvas API
- **Export:** ReportLab (PDF), built-in CSV

## Installation

### 1. Install Python Dependencies

```bash
cd pettycash-web

# Using pip
pip install -r requirements.txt

# OR using conda
conda install flask flask-sqlalchemy flask-login flask-wtf wtforms reportlab pillow python-dotenv
```

### 2. Run the Application

```bash
python app.py
```

The app will:
- Create the database automatically
- Seed with test users
- Start on `http://127.0.0.1:8000`

### 3. Login with Test Credentials

**Employee Account:**
- Email: `employee@example.com`
- Password: `password123`

**Senior Account:**
- Email: `senior@example.com`
- Password: `password123`

## Usage Guide

### For Employees

1. **Login** with employee credentials
2. **Create New Expense:**
   - Click "New Expense" button
   - Fill in purpose, amount, recipient name
   - Add recipient signature (draw on canvas)
   - Add your signature
   - Submit for approval

3. **View Your Expenses:**
   - Dashboard shows all your expenses
   - Click any expense to view details
   - Export to PDF for records

### For Seniors

1. **Login** with senior credentials
2. **Review Pending Approvals:**
   - Dashboard shows all pending expenses
   - Click expense to review details

3. **Approve Expense:**
   - Review expense details and signatures
   - Add your signature
   - Click "Approve Expense"

4. **Reject Expense:**
   - Provide rejection reason
   - Click "Reject Expense"

5. **Export Reports:**
   - Export all approved expenses to CSV
   - Export individual expense vouchers to PDF

## Project Structure

```
pettycash-web/
├── app.py                      # Main Flask application
├── models.py                   # Database models (User, Expense)
├── config.py                   # Configuration settings
├── requirements.txt            # Python dependencies
│
├── instance/
│   └── pettycash.db           # SQLite database (auto-created)
│
├── static/
│   ├── css/                   # Custom styles (optional)
│   ├── js/
│   │   └── signature.js       # Canvas signature capture
│   └── signatures/            # Saved signature images (auto-created)
│
└── templates/
    ├── base.html              # Base template with nav
    ├── login.html             # Login page
    ├── dashboard.html         # Role-based dashboard
    └── expenses/
        ├── list.html          # Expense list with filters
        ├── create.html        # Create new expense with signatures
        └── detail.html        # Expense details + approval

```

## Database Schema

### User Model
- `id` - Primary key
- `username` - Unique username
- `email` - Unique email for login
- `password_hash` - Hashed password (SHA256)
- `full_name` - Full display name
- `role` - 'employee' or 'senior'

### Expense Model
- `id` - Primary key
- `purpose` - Description of expense
- `amount` - Expense amount (float)
- `recipient_name` - Who received the money
- `status` - 'draft', 'pending', 'approved', 'rejected'
- `creator_id` - Foreign key to User
- `recipient_signature` - PNG filename
- `employee_signature` - PNG filename
- `senior_signature` - PNG filename
- `approved_by_id` - Foreign key to User (senior)
- `approved_at` - Approval timestamp
- `rejection_reason` - Text reason if rejected

## API Endpoints

### Authentication
- `GET/POST /login` - Login page
- `GET /logout` - Logout

### Dashboard
- `GET /` - Redirect to login or dashboard
- `GET /dashboard` - Role-based dashboard

### Expenses
- `GET /expenses` - List all expenses (filtered by role)
- `GET/POST /expenses/create` - Create new expense
- `GET /expenses/<id>` - View expense details
- `POST /expenses/<id>/approve` - Approve expense (senior only)
- `POST /expenses/<id>/reject` - Reject expense (senior only)

### Export
- `GET /export/csv` - Export expenses to CSV
- `GET /export/pdf/<id>` - Export single expense to PDF

## Security Features

- Password hashing with Werkzeug's `generate_password_hash`
- Session-based authentication with Flask-Login
- Role-based authorization checks
- CSRF protection with Flask-WTF (forms)
- Secure file handling for signatures

## Customization

### Change Secret Key (Production)

Edit `config.py`:

```python
SECRET_KEY = 'your-secure-random-key-here'
```

### Use PostgreSQL Instead of SQLite

Edit `config.py`:

```python
SQLALCHEMY_DATABASE_URI = 'postgresql://user:password@localhost/pettycash'
```

### Change Session Timeout

Edit `config.py`:

```python
PERMANENT_SESSION_LIFETIME = timedelta(hours=12)  # Default: 24 hours
```

## Development

### Add New User Manually

```python
python
>>> from app import app, db
>>> from models import User
>>> with app.app_context():
...     user = User(username='newuser', email='user@example.com', full_name='New User', role='employee')
...     user.set_password('password')
...     db.session.add(user)
...     db.session.commit()
```

### Reset Database

```bash
rm instance/pettycash.db
python app.py  # Will recreate with seed data
```

### Debug Mode

The app runs in debug mode by default (`debug=True` in `app.py`). Disable for production:

```python
app.run(debug=False, host='0.0.0.0', port=8000)
```

## Production Deployment

### Using Gunicorn

```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:8000 app:app
```

### Using Docker

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:8000", "app:app"]
```

## Troubleshooting

**Issue: Signatures not saving**
- Check that `static/signatures/` directory exists and is writable
- Ensure Pillow is installed: `pip install Pillow`

**Issue: PDF export fails**
- Install ReportLab: `pip install reportlab`
- Check file permissions

**Issue: Database errors**
- Delete `instance/pettycash.db` and restart app
- Check SQLite version: `sqlite3 --version`

## Future Enhancements

- [ ] Email notifications for approvals
- [ ] Advanced reporting dashboard
- [ ] Expense categories/tags
- [ ] Budget tracking
- [ ] Multi-currency support
- [ ] Receipt photo attachments
- [ ] Audit trail logging
- [ ] API for mobile apps

## License

MIT License - Free to use and modify

## Support

For issues or questions, please create an issue on GitHub or contact support.

---

**Built with ❤️ for PettyCash NYSA**
