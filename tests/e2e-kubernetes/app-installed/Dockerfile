FROM python:3.13-slim

WORKDIR /src
COPY checkout.py pyproject.toml /src/

RUN pip install --no-cache-dir /src

CMD ["checkout"]
