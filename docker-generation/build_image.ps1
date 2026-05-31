docker build -t zewail-smarthome:final -f docker/Dockerfile .
docker compose -f docker/docker-compose.yml up --build
