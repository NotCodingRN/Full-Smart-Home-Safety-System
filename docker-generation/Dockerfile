FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 SMARTHOME_APP_DIR=/app SMARTHOME_AWS_ENABLED=false SMARTHOME_LOCAL_MQTT_HOST=mosquitto
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 libgl1 libgomp1 curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY docker/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY code/raspberry_pi/ /app/
EXPOSE 5000
CMD ["python", "smarthome_daemon.py", "--dry-run"]
