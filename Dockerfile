# SecureData Central -- servidor MCP (stdio).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SDC_DB_PATH=/data/securedata.db

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY sdc/ ./sdc/

# Volume para o banco -- o container pode ser recriado sem perder dados.
RUN mkdir -p /data
VOLUME ["/data"]

# stdio: o processo fala MCP pelo stdin/stdout.
ENTRYPOINT ["python", "-m", "sdc.mcp.server"]
