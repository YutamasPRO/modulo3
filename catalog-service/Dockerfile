FROM python:3.11-slim

WORKDIR /app

# Copia requirements.txt (soporta contexto '.' y contexto './catalog-service')
COPY catalog-service/requirements.tx[t] requirements.tx[t] ./

RUN pip install --no-cache-dir -r requirements.txt

# Copia el código fuente (soporta contexto '.' y contexto './catalog-service')
COPY . /tmp/build/
RUN if [ -d "/tmp/build/catalog-service" ]; then \
        cp -r /tmp/build/catalog-service/* .; \
    else \
        cp -r /tmp/build/* .; \
    fi && rm -rf /tmp/build

EXPOSE 8001

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8001}"]
