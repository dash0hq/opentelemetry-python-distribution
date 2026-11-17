FROM python:3.15-slim

WORKDIR /src
COPY checkout.py pyproject.toml /src/

RUN pip install --no-cache-dir /src

CMD ["checkout"]
