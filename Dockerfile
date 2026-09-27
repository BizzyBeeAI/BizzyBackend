FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend ./backend
ADD docker/bizzydata-demo.tar.gz ./data/demo/

ENV BIZZY_DATA_DIR=/app/data/demo \
    BIZZY_AS_OF_DATE=2026-09-23

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
