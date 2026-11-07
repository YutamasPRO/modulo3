FROM python:3.11-slim

WORKDIR /app

# Copia requirements.txt (soporta contexto '.' y contexto './orders-service')
COPY orders-service/requirements.tx[t] requirements.tx[t] ./

RUN pip install --no-cache-dir -r requirements.txt

# Copia el código fuente (soporta contexto '.' y contexto './orders-service')
COPY . /tmp/build/
RUN if [ -d "/tmp/build/orders-service" ]; then \
        cp -r /tmp/build/orders-service/* .; \
    else \
        cp -r /tmp/build/* .; \
    fi && rm -rf /tmp/build

EXPOSE 8002

CMD ["sh", "-c", "python -m alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port ${PORT:-8002}"]
