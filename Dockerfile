FROM python:3.11-trixie

# Python runtime settings
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# System deps and TA-Lib (needed by talib)
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    tzdata \
 && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --upgrade pip

WORKDIR /app

# Install Python dependencies first (better layer caching)
COPY requirements.txt ./
RUN pip install -r requirements.txt

# Copy application code
COPY main.py ./

# # Default command
CMD ["python", "main.py"]
