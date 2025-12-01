# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PettyCash NYSA is a Flask web application for expense management with a triple digital signature workflow. The system enforces a role-based approval process where employees create expenses, and seniors approve/reject them.

## Common Commands

### Development
```bash
# Install dependencies
pip install -r requirements.txt
# OR
conda install flask flask-sqlalchemy flask-login flask-wtf wtforms reportlab pillow python-dotenv

# Run the application (starts on http://127.0.0.1:8000)
python app.py

# Reset database (deletes all data and recreates with seed users)
rm instance/pettycash.db
python app.py
```

### Test Users (created automatically on first run)
- **Employee**: employee@example.com / password123
- **Senior**: senior@example.com / password123

### Production Deployment
```bash
# Using Gunicorn
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:8000 app:app
```

### Manual Database Operations
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

## Architecture

### Core Workflow
1. **Employee** creates expense with recipient signature and their own signature
2. Expense status: `draft` → `pending` (submitted for approval)
3. **Senior** reviews pending expenses and either:
   - Approves with their digital signature → status: `approved`
   - Rejects with a reason → status: `rejected`

### Role-Based Access
- **Employees** (`role='employee'`): Can only create expenses and view their own
- **Seniors** (`role='senior'`): Can view all expenses, approve/reject pending ones, cannot create expenses

### Application Structure
- **Single-file pattern**: All routes are in `app.py`, organized by sections:
  - Authentication routes (`/login`, `/logout`)
  - Dashboard (`/dashboard` - role-specific view)
  - Expense CRUD (`/expenses/*`)
  - Export routes (`/export/csv`, `/export/pdf/<id>`)

- **Models** (`models.py`):
  - `User`: Authentication with `UserMixin`, role property (`is_senior`, `is_employee`)
  - `Expense`: Tracks status, three signature file paths, approval metadata

- **Config** (`config.py`):
  - Environment-aware configuration for Railway deployment
  - Handles PostgreSQL URL conversion for psycopg3
  - Switches between `/tmp` (Railway) and `instance/` (local) for database
  - Switches between `/data/signatures` (Railway volume) and `static/signatures` (local)

### Digital Signature System
- **HTML5 Canvas** (`static/js/signature.js`): Capture signatures as base64 data URLs
- **Server-side** (`save_signature_image()` in app.py):
  - Converts base64 → PNG using Pillow
  - Stores in `static/signatures/` with unique UUID filenames
  - Returns filename to store in database

### Export Functionality
- **CSV Export**: All approved expenses (seniors) or user's own expenses (employees)
- **PDF Export**: Individual expense voucher with ReportLab, includes signature images

## Database

### SQLite (Development)
- Location: `instance/pettycash.db`
- Auto-created on first run with seed data

### PostgreSQL (Production)
- Set `DATABASE_URL` environment variable
- Config automatically converts `postgresql://` → `postgresql+psycopg://` for psycopg3

### Key Relationships
- `User.expenses_created` → `Expense.creator` (one-to-many)
- `Expense.approved_by` → `User` (many-to-one, nullable)

## Important Notes

### Authorization Patterns
All expense detail views check:
```python
if not current_user.is_senior and expense.creator_id != current_user.id:
    # Deny access
```

Approval/rejection routes verify:
```python
if not current_user.is_senior:
    # Deny access
```

### File Storage
- Signatures stored as PNG files in `UPLOAD_FOLDER` (configurable in `config.py`)
- Filenames use UUIDs to prevent collisions: `{sig_type}_{uuid}.png`
- Ensure `static/signatures/` directory exists and is writable

### Deployment Considerations
- Change `SECRET_KEY` in production (use environment variable)
- Disable debug mode: `app.run(debug=False, ...)`
- For Railway: Database uses `/tmp` (ephemeral), signatures use `/data` (volume-mounted)
- Session lifetime: 24 hours (configurable in `config.py`)
