FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install --no-install-recommends -y ffmpeg fonts-nanum fontconfig \
    && fc-cache -f \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt backend/requirements-cloud.txt ./
RUN pip install --no-cache-dir --upgrade -r requirements-cloud.txt

COPY backend/app ./app

EXPOSE 8080

CMD ["sh", "-c", "exec fastapi run app/main.py --host 0.0.0.0 --port ${PORT:-8080}"]
