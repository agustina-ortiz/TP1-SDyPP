# Imagen del nodo D (registro de contactos). Es el unico que se despliega:
# los nodos C corren en las maquinas del grupo durante la demo.
FROM python:3.11-slim

WORKDIR /app

# Las dependencias primero, para que Docker cachee esta capa entre builds.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY common/ ./common/
COPY hit7/ ./hit7/

# Cloud Run y Render inyectan el puerto por variable de entorno.
ENV PORT=8000
ENV LOG_DIR=/app/logs
EXPOSE 8000

CMD ["sh", "-c", "python -m hit7.nodo_d --host 0.0.0.0 --port ${PORT}"]
