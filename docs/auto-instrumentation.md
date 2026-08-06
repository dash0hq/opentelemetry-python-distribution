# Auto-instrumentation

## How it works

The distribution depends on the full set of upstream auto-instrumentation packages, all pinned to a single contrib version.
When `opentelemetry-instrument` starts your application, each installed instrumentor is activated automatically.
Instrumentors whose target library is not installed are silently skipped.
**No `opentelemetry-bootstrap` step is required.**

## Defensive loading

Each instrumentor is loaded defensively: if one fails (due to a version incompatibility, a missing dependency, or a bug), the failure is logged and the instrumentor is skipped.
Instrumentation of the rest of the process continues.
A single broken instrumentor does not abort the entire auto-instrumentation process.

## Supported libraries and frameworks

### Web frameworks

<div class="two-col-lib-table">

| Library | Instrumentation package |
|---|---|
| Flask | [`opentelemetry-instrumentation-flask`](https://pypi.org/project/opentelemetry-instrumentation-flask/) |
| Django | [`opentelemetry-instrumentation-django`](https://pypi.org/project/opentelemetry-instrumentation-django/) |
| FastAPI | [`opentelemetry-instrumentation-fastapi`](https://pypi.org/project/opentelemetry-instrumentation-fastapi/) |
| Falcon | [`opentelemetry-instrumentation-falcon`](https://pypi.org/project/opentelemetry-instrumentation-falcon/) |
| Pyramid | [`opentelemetry-instrumentation-pyramid`](https://pypi.org/project/opentelemetry-instrumentation-pyramid/) |
| Starlette | [`opentelemetry-instrumentation-starlette`](https://pypi.org/project/opentelemetry-instrumentation-starlette/) |
| Tornado | [`opentelemetry-instrumentation-tornado`](https://pypi.org/project/opentelemetry-instrumentation-tornado/) |
| ASGI | [`opentelemetry-instrumentation-asgi`](https://pypi.org/project/opentelemetry-instrumentation-asgi/) |
| WSGI | [`opentelemetry-instrumentation-wsgi`](https://pypi.org/project/opentelemetry-instrumentation-wsgi/) |

</div>

### HTTP clients

<div class="two-col-lib-table">

| Library | Instrumentation package |
|---|---|
| aiohttp client | [`opentelemetry-instrumentation-aiohttp-client`](https://pypi.org/project/opentelemetry-instrumentation-aiohttp-client/) |
| aiohttp server | [`opentelemetry-instrumentation-aiohttp-server`](https://pypi.org/project/opentelemetry-instrumentation-aiohttp-server/) |
| httpx | [`opentelemetry-instrumentation-httpx`](https://pypi.org/project/opentelemetry-instrumentation-httpx/) |
| requests | [`opentelemetry-instrumentation-requests`](https://pypi.org/project/opentelemetry-instrumentation-requests/) |
| urllib | [`opentelemetry-instrumentation-urllib`](https://pypi.org/project/opentelemetry-instrumentation-urllib/) |
| urllib3 | [`opentelemetry-instrumentation-urllib3`](https://pypi.org/project/opentelemetry-instrumentation-urllib3/) |

</div>

### Databases and caches

<div class="two-col-lib-table">

| Library | Instrumentation package |
|---|---|
| psycopg2 (PostgreSQL) | [`opentelemetry-instrumentation-psycopg2`](https://pypi.org/project/opentelemetry-instrumentation-psycopg2/) |
| psycopg (PostgreSQL) | [`opentelemetry-instrumentation-psycopg`](https://pypi.org/project/opentelemetry-instrumentation-psycopg/) |
| asyncpg (async PostgreSQL) | [`opentelemetry-instrumentation-asyncpg`](https://pypi.org/project/opentelemetry-instrumentation-asyncpg/) |
| aiopg (async PostgreSQL) | [`opentelemetry-instrumentation-aiopg`](https://pypi.org/project/opentelemetry-instrumentation-aiopg/) |
| mysql-connector-python | [`opentelemetry-instrumentation-mysql`](https://pypi.org/project/opentelemetry-instrumentation-mysql/) |
| mysqlclient | [`opentelemetry-instrumentation-mysqlclient`](https://pypi.org/project/opentelemetry-instrumentation-mysqlclient/) |
| PyMySQL | [`opentelemetry-instrumentation-pymysql`](https://pypi.org/project/opentelemetry-instrumentation-pymysql/) |
| pymssql (SQL Server) | [`opentelemetry-instrumentation-pymssql`](https://pypi.org/project/opentelemetry-instrumentation-pymssql/) |
| SQLite3 | [`opentelemetry-instrumentation-sqlite3`](https://pypi.org/project/opentelemetry-instrumentation-sqlite3/) |
| PyMongo (MongoDB) | [`opentelemetry-instrumentation-pymongo`](https://pypi.org/project/opentelemetry-instrumentation-pymongo/) |
| Cassandra / ScyllaDB | [`opentelemetry-instrumentation-cassandra`](https://pypi.org/project/opentelemetry-instrumentation-cassandra/) |
| Redis | [`opentelemetry-instrumentation-redis`](https://pypi.org/project/opentelemetry-instrumentation-redis/) |
| pymemcache | [`opentelemetry-instrumentation-pymemcache`](https://pypi.org/project/opentelemetry-instrumentation-pymemcache/) |
| DB-API 2.0 | [`opentelemetry-instrumentation-dbapi`](https://pypi.org/project/opentelemetry-instrumentation-dbapi/) |

</div>

### ORMs and query builders

<div class="two-col-lib-table">

| Library | Instrumentation package |
|---|---|
| SQLAlchemy | [`opentelemetry-instrumentation-sqlalchemy`](https://pypi.org/project/opentelemetry-instrumentation-sqlalchemy/) |
| TortoiseORM | [`opentelemetry-instrumentation-tortoiseorm`](https://pypi.org/project/opentelemetry-instrumentation-tortoiseorm/) |

</div>

### Message queues and task queues

<div class="two-col-lib-table">

| Library | Instrumentation package |
|---|---|
| confluent-kafka | [`opentelemetry-instrumentation-confluent-kafka`](https://pypi.org/project/opentelemetry-instrumentation-confluent-kafka/) |
| kafka-python | [`opentelemetry-instrumentation-kafka-python`](https://pypi.org/project/opentelemetry-instrumentation-kafka-python/) |
| aiokafka | [`opentelemetry-instrumentation-aiokafka`](https://pypi.org/project/opentelemetry-instrumentation-aiokafka/) |
| aio-pika (RabbitMQ) | [`opentelemetry-instrumentation-aio-pika`](https://pypi.org/project/opentelemetry-instrumentation-aio-pika/) |
| pika (RabbitMQ) | [`opentelemetry-instrumentation-pika`](https://pypi.org/project/opentelemetry-instrumentation-pika/) |
| Celery | [`opentelemetry-instrumentation-celery`](https://pypi.org/project/opentelemetry-instrumentation-celery/) |
| Remoulade | [`opentelemetry-instrumentation-remoulade`](https://pypi.org/project/opentelemetry-instrumentation-remoulade/) |
| AWS SQS (boto3sqs) | [`opentelemetry-instrumentation-boto3sqs`](https://pypi.org/project/opentelemetry-instrumentation-boto3sqs/) |

</div>

### Async and concurrency

<div class="two-col-lib-table">

| Library | Instrumentation package |
|---|---|
| asyncio | [`opentelemetry-instrumentation-asyncio`](https://pypi.org/project/opentelemetry-instrumentation-asyncio/) |
| threading | [`opentelemetry-instrumentation-threading`](https://pypi.org/project/opentelemetry-instrumentation-threading/) |

</div>

### CLI frameworks

<div class="two-col-lib-table">

| Library | Instrumentation package |
|---|---|
| Click | [`opentelemetry-instrumentation-click`](https://pypi.org/project/opentelemetry-instrumentation-click/) |
| asyncclick | [`opentelemetry-instrumentation-asyncclick`](https://pypi.org/project/opentelemetry-instrumentation-asyncclick/) |

</div>

### AI and cloud

<div class="two-col-lib-table">

| Library | Instrumentation package |
|---|---|
| OpenAI | [`opentelemetry-instrumentation-openai-v2`](https://pypi.org/project/opentelemetry-instrumentation-openai-v2/) |
| Google Vertex AI | [`opentelemetry-instrumentation-vertexai`](https://pypi.org/project/opentelemetry-instrumentation-vertexai/) |
| boto3 / botocore (AWS SDK) | [`opentelemetry-instrumentation-botocore`](https://pypi.org/project/opentelemetry-instrumentation-botocore/) |

</div>

### Other

<div class="two-col-lib-table">

| Library | Instrumentation package |
|---|---|
| gRPC | [`opentelemetry-instrumentation-grpc`](https://pypi.org/project/opentelemetry-instrumentation-grpc/) |
| Jinja2 | [`opentelemetry-instrumentation-jinja2`](https://pypi.org/project/opentelemetry-instrumentation-jinja2/) |
| logging | [`opentelemetry-instrumentation-logging`](https://pypi.org/project/opentelemetry-instrumentation-logging/) |
| structlog | [`opentelemetry-instrumentation-structlog`](https://pypi.org/project/opentelemetry-instrumentation-structlog/) |
| System metrics | [`opentelemetry-instrumentation-system-metrics`](https://pypi.org/project/opentelemetry-instrumentation-system-metrics/) |
| Exception handling | [`opentelemetry-instrumentation-exceptions`](https://pypi.org/project/opentelemetry-instrumentation-exceptions/) |

</div>

## Propagators

The AWS X-Ray propagator ([`opentelemetry-propagator-aws-xray`](https://pypi.org/project/opentelemetry-propagator-aws-xray/)) is explicitly included.
The W3C TraceContext and Baggage propagators are built into the OpenTelemetry SDK and always available.
B3 format propagation is not included; it requires the separate [`opentelemetry-propagator-b3`](https://pypi.org/project/opentelemetry-propagator-b3/) package, which is not a dependency of this distribution.

## What is not included

The following packages are deliberately excluded:

- [`opentelemetry-exporter-prometheus`](https://pypi.org/project/opentelemetry-exporter-prometheus/): not needed; OTLP metrics export covers this use case.
- [`opentelemetry-propagator-ot-trace`](https://pypi.org/project/opentelemetry-propagator-ot-trace/): legacy propagator not required for Dash0.
- [`opentelemetry-instrumentation-aws-lambda`](https://pypi.org/project/opentelemetry-instrumentation-aws-lambda/): Lambda deployments use a dedicated instrumentation layer.
