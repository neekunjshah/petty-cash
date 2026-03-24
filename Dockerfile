FROM python:3.12-slim

WORKDIR /app

# Install deps first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY . .

# Create data directory for SQLite + signatures
RUN mkdir -p /app/data /app/static/signatures

# Expose the app port
EXPOSE 8084

# Run with gunicorn
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:8084", "app:app"]
