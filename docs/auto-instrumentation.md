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

| Library | Instrumentation package |
|---|---|
| Flask | `opentelemetry-instrumentation-flask` |
| Django | `opentelemetry-instrumentation-django` |
| FastAPI | `opentelemetry-instrumentation-fastapi` |
| Falcon | `opentelemetry-instrumentation-falcon` |
| Pyramid | `opentelemetry-instrumentation-pyramid` |
| Starlette | `opentelemetry-instrumentation-starlette` |
| Tornado | `opentelemetry-instrumentation-tornado` |
| ASGI | `opentelemetry-instrumentation-asgi` |
| WSGI | `opentelemetry-instrumentation-wsgi` |

### HTTP clients

| Library | Instrumentation package |
|---|---|
| aiohttp client | `opentelemetry-instrumentation-aiohttp-client` |
| aiohttp server | `opentelemetry-instrumentation-aiohttp-server` |
| httpx | `opentelemetry-instrumentation-httpx` |
| requests | `opentelemetry-instrumentation-requests` |
| urllib | `opentelemetry-instrumentation-urllib` |
| urllib3 | `opentelemetry-instrumentation-urllib3` |

### Databases and caches

| Library | Instrumentation package |
|---|---|
| psycopg2 (PostgreSQL) | `opentelemetry-instrumentation-psycopg2` |
| psycopg (PostgreSQL) | `opentelemetry-instrumentation-psycopg` |
| asyncpg (async PostgreSQL) | `opentelemetry-instrumentation-asyncpg` |
| aiopg (async PostgreSQL) | `opentelemetry-instrumentation-aiopg` |
| mysql-connector-python | `opentelemetry-instrumentation-mysql` |
| mysqlclient | `opentelemetry-instrumentation-mysqlclient` |
| PyMySQL | `opentelemetry-instrumentation-pymysql` |
| pymssql (SQL Server) | `opentelemetry-instrumentation-pymssql` |
| SQLite3 | `opentelemetry-instrumentation-sqlite3` |
| PyMongo (MongoDB) | `opentelemetry-instrumentation-pymongo` |
| Cassandra / ScyllaDB | `opentelemetry-instrumentation-cassandra` |
| Redis | `opentelemetry-instrumentation-redis` |
| pymemcache | `opentelemetry-instrumentation-pymemcache` |
| DB-API 2.0 | `opentelemetry-instrumentation-dbapi` |

### ORMs and query builders

| Library | Instrumentation package |
|---|---|
| SQLAlchemy | `opentelemetry-instrumentation-sqlalchemy` |
| TortoiseORM | `opentelemetry-instrumentation-tortoiseorm` |

### Message queues and task queues

| Library | Instrumentation package |
|---|---|
| confluent-kafka | `opentelemetry-instrumentation-confluent-kafka` |
| kafka-python | `opentelemetry-instrumentation-kafka-python` |
| aiokafka | `opentelemetry-instrumentation-aiokafka` |
| aio-pika (RabbitMQ) | `opentelemetry-instrumentation-aio-pika` |
| pika (RabbitMQ) | `opentelemetry-instrumentation-pika` |
| Celery | `opentelemetry-instrumentation-celery` |
| Remoulade | `opentelemetry-instrumentation-remoulade` |
| AWS SQS (boto3sqs) | `opentelemetry-instrumentation-boto3sqs` |

### Async and concurrency

| Library | Instrumentation package |
|---|---|
| asyncio | `opentelemetry-instrumentation-asyncio` |
| threading | `opentelemetry-instrumentation-threading` |

### CLI frameworks

| Library | Instrumentation package |
|---|---|
| Click | `opentelemetry-instrumentation-click` |
| asyncclick | `opentelemetry-instrumentation-asyncclick` |

### AI and cloud

| Library | Instrumentation package |
|---|---|
| OpenAI | `opentelemetry-instrumentation-openai-v2` |
| Google Vertex AI | `opentelemetry-instrumentation-vertexai` |
| boto3 / botocore (AWS SDK) | `opentelemetry-instrumentation-botocore` |

### Other

| Library | Instrumentation package |
|---|---|
| gRPC | `opentelemetry-instrumentation-grpc` |
| Jinja2 | `opentelemetry-instrumentation-jinja2` |
| logging | `opentelemetry-instrumentation-logging` |
| structlog | `opentelemetry-instrumentation-structlog` |
| System metrics | `opentelemetry-instrumentation-system-metrics` |
| Exception handling | `opentelemetry-instrumentation-exceptions` |

## Propagators

The AWS X-Ray propagator (`opentelemetry-propagator-aws-xray`) is explicitly included.
The W3C TraceContext and Baggage propagators are built into the OpenTelemetry SDK and always available.
B3 format propagation is not included; it requires the separate `opentelemetry-propagator-b3` package, which is not a dependency of this distribution.

## What is not included

The following packages are deliberately excluded:

- `opentelemetry-exporter-prometheus`: not needed; OTLP metrics export covers this use case.
- `opentelemetry-propagator-ot-trace`: legacy propagator not required for Dash0.
- `opentelemetry-instrumentation-aws-lambda`: Lambda deployments use a dedicated instrumentation layer.
