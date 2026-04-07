FROM python:3.11-slim

WORKDIR /app
COPY server.py .

ENV PORT=8080
ENV STARTUP_DELAY_SECONDS=10

EXPOSE 8080

CMD ["python", "server.py"]
