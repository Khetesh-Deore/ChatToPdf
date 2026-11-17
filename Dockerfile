# The Playwright base image version must match the playwright pip package version.
# Pin both together — bump them together when upgrading.
FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy

# Install Noto fonts (Hindi, CJK, emoji) + DejaVu (code) + npm (for KaTeX vendor step)
RUN apt-get update && apt-get install -y --no-install-recommends \
      fonts-noto-core \
      fonts-noto-cjk \
      fonts-noto-color-emoji \
      fonts-dejavu-core \
      npm \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

# Install Python deps first (layer-cached unless requirements.txt changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Vendor KaTeX offline (needs npm, runs once at build time)
RUN bash scripts/vendor_katex.sh

# Non-root user for safety
RUN useradd -m appuser && chown -R appuser /srv
USER appuser

EXPOSE 8000

# --workers 1 keeps a single Chromium process; scale via multiple containers instead.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
