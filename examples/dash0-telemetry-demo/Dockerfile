FROM python:3.13-slim

WORKDIR /src
COPY storefront.py pyproject.toml /src/

RUN pip install --no-cache-dir /src

CMD ["storefront"]
