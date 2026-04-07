FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create data directory for SQLite persistence
RUN mkdir -p /app/data

# Expose HF Spaces default port
EXPOSE 7860

# Run with gunicorn
CMD ["gunicorn", "-w", "2", "--timeout", "120", "-b", "0.0.0.0:7860", "app:app"]
