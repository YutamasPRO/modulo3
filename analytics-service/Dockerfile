FROM python:3.11-slim

WORKDIR /app

# Copia requirements.txt (soporta contexto '.' y contexto './analytics-service')
COPY analytics-service/requirements.tx[t] requirements.tx[t] ./

RUN pip install --no-cache-dir -r requirements.txt

# Copia el código fuente (soporta contexto '.' y contexto './analytics-service')
COPY . /tmp/build/
RUN if [ -d "/tmp/build/analytics-service" ]; then \
        cp -r /tmp/build/analytics-service/* .; \
    else \
        cp -r /tmp/build/* .; \
    fi && rm -rf /tmp/build

EXPOSE 8003

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8003}"]
