FROM python:3.13-slim

RUN pip install --no-cache-dir "flask==3.1.*"

WORKDIR /app
COPY checkout.py /app/checkout.py

EXPOSE 8080
CMD ["python", "/app/checkout.py"]
