ARG python_version=3.13

FROM python:${python_version}-slim AS build
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
RUN pip install --no-cache-dir uv
WORKDIR /src
COPY . /src
RUN uv build --all-packages --out-dir /wheels

FROM python:${python_version}-slim
ARG case
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV PYTHONUNBUFFERED=1
COPY --from=build /wheels /wheels
COPY tests/e2e-instrumentations/cases/${case}/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir /wheels/*.whl -r /tmp/requirements.txt
COPY tests/e2e-instrumentations/assert_local_install.py /assert_local_install.py
RUN python /assert_local_install.py
COPY tests/e2e-instrumentations/run_case.py /run_case.py
COPY tests/e2e-instrumentations/cases/${case}/app.py /app/app.py
WORKDIR /app
CMD ["python", "/run_case.py"]
