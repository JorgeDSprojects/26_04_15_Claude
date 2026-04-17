FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir aiomqtt==2.3.0 pydantic-settings==2.3.0 structlog==24.1.0

COPY app/ app/

CMD ["python", "-m", "app.main"]
