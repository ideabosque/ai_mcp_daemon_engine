# AI MCP Daemon Engine

## Overview

**AI MCP Daemon Engine** is a thin daemon and CLI that exposes the [Model Context Protocol (MCP)](https://github.com/model-context-protocol/mcp) over HTTP **Server‑Sent Events (SSE)** or **STDIO**.

It bundles a FastAPI application that can:

* Stream assistant responses to browsers or other services via SSE
* Execute MCP *tools*, *resources* and *prompts* defined in an external JSON configuration
* Persist function metadata in DynamoDB through the **SilvaEngine** data layer
* Authenticate users with either **local JWTs** or **AWS Cognito**
* Dynamically download and extract Python functions from S3, allowing serverless style extensions

---

## Features

* **Pluggable Transport –** `jsonrpc/sse` (default) or `stdio` for embedded/PIPE use‑cases
* **Authentication –** Local JWT (with bcrypt‑hashed users) *or* Cognito JWT validation
* **GraphQL API –** CRUD operations for MCP functions and invocations (`mcp_core_graphql`)
* **Live Event Bus –** Replay‑buffered SSE stream with heartbeat and per‑user fan‑out
* **AWS Integrations –** S3 function bundles & DynamoDB storage via SilvaEngine helpers
* **Simple CLI** – `mcp‑daemon` starts the server with one command

---

## Directory Layout

```text
ai_mcp_daemon_engine/
├── ai_mcp_daemon_engine/
│   ├── handlers/        # FastAPI, auth, SSE, utility helpers
│   ├── mutations/       # GraphQL mutations
│   ├── queries/         # GraphQL queries
│   ├── models/          # Pydantic / Graphene models
│   ├── main.py          # CLI entry‑point
│   └── __init__.py
├── pyproject.toml       # Build metadata & dependencies
└── README.md            # You are here
```

---

## Quick Start (Local JWT + SSE)

```bash
# Clone and install editable
$ git clone https://github.com/your‑org/ai_mcp_daemon_engine.git
$ cd ai_mcp_daemon_engine
$ python -m venv .venv && source .venv/bin/activate
$ pip install -e .

# Minimal env‑vars
export MCP_TRANSPORT=sse
export PORT=8000
export AUTH_PROVIDER=local
export ADMIN_USERNAME=admin
export ADMIN_PASSWORD=changeme

# Fire up the daemon
mcp-daemon
```

Visit `http://localhost:8000/docs` for interactive OpenAPI docs or connect to the SSE endpoint:

```bash
curl -N http://localhost:8000/default/mcp -H "Authorization: Bearer <token>"
```

---

## Running with AWS Cognito

```bash
export AUTH_PROVIDER=cognito
export COGNITO_USER_POOL_ID="us-west-2_abc123"
export COGNITO_APP_CLIENT_ID="abcd1234"
export COGNITO_APP_SECRET="shhhh"
export COGNITO_JWKS_URL="https://cognito-idp.us-west-2.amazonaws.com/us-west-2_abc123/.well-known/jwks.json"

mcp-daemon
```

---

## Environment Variables

| Variable                                      | Default          | Description                                   |
| --------------------------------------------- | ---------------- | --------------------------------------------- |
| `MCP_TRANSPORT`                               | `sse`            | `jsonrpc/sse` (FastAPI) or `stdio` (pipe)     |
| `PORT`                                        | `8000`           | Listening port when using `jsonrpc/sse`       |
| `MCP_CONFIG_FILE`                             |  —               | Path to JSON defining tools/resources/prompts |
| `AUTH_PROVIDER`                               | `local`          | `local` or `cognito`                          |
| `LOCAL_USER_FILE`                             | `users.json`     | Local user DB (bcrypt‑hashed)                 |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD`           | admin / admin123 | Bootstrap super‑admin                         |
| `ADMIN_STATIC_TOKEN`                          |  —               | Hard‑coded bearer token that bypasses login   |
| `JWT_SECRET_KEY`                              | CHANGEME         | HMAC secret for local JWTs                    |
| `ACCESS_TOKEN_EXP`                            | 15               | Token expiry in minutes                       |
| `COGNITO_*`                                   |  —               | Required when `AUTH_PROVIDER=cognito`         |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` |  —               | For DynamoDB / S3 access                      |
| `REGION_NAME`                                 | us‑east‑1        | AWS region                                    |
| `FUNCT_BUCKET_NAME`                           |  —               | S3 bucket storing zipped function bundles     |
| `FUNCT_ZIP_PATH`                              |  —               | Where are the zip files stored locally        |
| `FUNCT_EXTRACT_PATH`                          | `/tmp/functions` | Where bundles are extracted locally           |

---

## Configuration File (MCP)

Supply a JSON blob that describes the endpoint’s capabilities and set its path via `MCP_CONFIG_FILE`:

```json
{
    "tools": {
        "tools": [
            {
                "name": "hello",
                "description": "Greet someone",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Name",
                            "default": "World"
                        }
                    }
                },
                "annotations": null
            },
            {
                "name": "add_numbers",
                "description": "Add two numbers",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "a": {
                            "type": "integer",
                            "description": "First number"
                        },
                        "b": {
                            "type": "integer",
                            "description": "Second number"
                        }
                    },
                    "required": [
                        "a",
                        "b"
                    ]
                },
                "annotations": null
            }
        ],
        "tool_modules": [
            {
                "name": "hello",
                "module_name": "mcp_function_demo",
                "function_name": "hello",
                "setting": {},
                "return_type": "text"
            },
            {
                "name": "add_numbers",
                "module_name": "mcp_function_demo",
                "function_name": "add_numbers",
                "setting": {},
                "return_type": "text"
            }
        ]
    },
    "resources": {
        "resources": [
            {
                "uri": "status://server",
                "name": "Server Status",
                "description": "Status info",
                "mimeType": "text/plain",
                "size": null,
                "annotations": null
            }
        ],
        "resource_modules": [
            {
                "name": "Server Status",
                "module_name": "mcp_function_demo",
                "function_name": "read_resource",
                "setting": {}
            }
        ]
    },
    "prompts": {
        "prompts": [
            {
                "name": "example-prompt",
                "description": "An example prompt template",
                "arguments": [
                    {
                        "name": "arg1",
                        "description": "Example argument",
                        "required": true
                    }
                ]
            }
        ],
        "prompt_modules": [
            {
                "name": "example-prompt",
                "module_name": "mcp_function_demo",
                "function_name": "get_prompt",
                "setting": {}
            }
        ]
    }
}
```

---

## CLI Reference

```bash
mcp-daemon              # start the SSE server
mcp-daemon --help       # show command options (transport, port, etc.)
```

---

## API Highlights

| Method | Path           | Purpose                   |
| ------ | -------------- | ------------------------- |
| `POST` | `/auth/login`  | Obtain JWT (local)        |
| `GET`  | `/jsonrpc/sse` | Connect to the SSE stream |
| `POST` | `/mcp`         | Process MCP messages      |
| `GET`  | `/graphql`     | GraphQL Playground (dev)  |

OpenAPI is served at `/docs` and ReDoc at `/redoc`.

---

## Development & Testing

```bash
pip install -e ".[dev]"
pytest
```

---

## Deployment Tips

* **Docker** – multi‑stage build; expose `$PORT` (default 8000).
* **AWS Fargate / ECS** – stateless; mount S3 via SDK.
* **Kubernetes** – use ConfigMap/Secret for env‑vars; readiness probe on `/docs`.

Use `MCP_TRANSPORT=stdio` to embed the daemon into another Python process.

---

## License

Distributed under the MIT License. See `LICENSE` for more information.

---

## Acknowledgements

* [Model Context Protocol](https://github.com/model-context-protocol/mcp)
* [FastAPI](https://fastapi.tiangolo.com/)
* [SilvaEngine Utility](https://pypi.org/project/SilvaEngine-Utility/)
* [AWS Cognito](https://aws.amazon.com/cognito/)
