FROM python:3.13-slim AS build

RUN pip install --no-cache-dir uv packaging

WORKDIR /src
COPY . /src

RUN uv build --all-packages --out-dir /wheels

RUN pip install --no-cache-dir --target /dash0 --find-links /wheels dash0-opentelemetry

RUN cp /dash0/dash0/opentelemetry/injector/sitecustomize.py /dash0/sitecustomize.py

RUN python /src/scripts/generate_all_dependencies.py /dash0 -o /dash0/all-dependencies.txt \
 && cat /dash0/all-dependencies.txt

FROM busybox:1.37
COPY --from=build /dash0 /dash0
