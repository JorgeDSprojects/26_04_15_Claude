FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

COPY . .

RUN chmod +x entrypoint.sh

CMD ["./entrypoint.sh"]
