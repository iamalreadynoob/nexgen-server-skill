# Nexgen Server API reference

Complete endpoint reference for Nexgen Server `/api/v1`. Read the section you need.

## Contents

1. [Common rules](#common-rules)
2. [Actuators](#actuators)
3. [Data](#data)
4. [Contents](#contents)
5. [Health](#health)
6. [Errors](#errors)
7. [Code examples](#code-examples)

---

## Common rules

- **Base URL:** `http://<host>:8000/api/v1`
- **Auth:** header `X-API-Key: <key>` on every endpoint except health, when the server has `API_KEY` set. Missing or wrong key → `401`. If the server has no key configured, the header is ignored.
- **Request ID:** optional `X-Request-ID` header; echoed back in the response and written to the server log. Useful when asking an operator to trace a failure.
- **IDs:** MongoDB ObjectIds as 24-char hex strings. An invalid ID returns `404`, not `422`.
  - Actuator ID key in responses: **`_id`**
  - Data and content ID key: **`id`**
- **Timestamps:** `created_at`, `updated_at`, UTC ISO 8601.
- **Soft delete:** `DELETE` sets `active: false`. The item disappears from every response. The `active` field is never returned.
- **Pagination (all list endpoints):**

  | Param | Type | Default | Notes |
  |---|---|---|---|
  | `page` | int | `1` | First page is 1 |
  | `limit` | int | `10` | Items per page |
  | `ascending` | bool | `false` | `false` = newest first (sort by `_id`) |

  List responses carry `total` (all matches) plus the items of the requested page.

---

## Actuators

A versioned, named Python method. `actuator_type` is `coding` (source → transmitted representation) or `decoding` (received representation → reconstruction or task decision).

| Method | Path | Purpose |
|---|---|---|
| GET | `/actuators` | List |
| GET | `/actuators/{actuator_id}` | Get by ID |
| GET | `/actuators/{actuator_name}/latest` | Get latest version of a name |
| POST | `/actuators` | Create |
| PUT | `/actuators/{actuator_id}` | Mark as latest (promote / roll back) |
| DELETE | `/actuators/{actuator_id}` | Soft delete |

### Actuator object

| Field | Type | Notes |
|---|---|---|
| `_id` | string | ID |
| `name` | string | 1–64 chars |
| `version` | string | 1–128 chars, free-form (semver recommended) |
| `actuator_type` | string | `coding` \| `decoding` |
| `requirements` | string[] | Python packages, e.g. `["numpy==2.1.0"]` |
| `method` | string | Python source code |
| `method_args` | object \| null | `{arg_name: {key: value}}`, e.g. `{"text": {"type": "str", "description": "..."}}` |
| `latest` | bool | Exactly one active version per name is `true` |
| `created_at`, `updated_at` | string | UTC |

### GET /actuators

Extra query param: `latest` (bool, optional). `true` → only latest versions; `false` → only non-latest. Omit for all.

Response `200`: `{"total": N, "actuators": [ ... ]}`

### GET /actuators/{actuator_id}

`200` actuator · `404` no active actuator with that ID.

### GET /actuators/{actuator_name}/latest

The version transmitter and receiver must both use. `200` actuator · `404` no active actuator of that name has `latest: true`.

### POST /actuators

| Field | Type | Required | Notes |
|---|---|---|---|
| `name` | string | yes | 1–64 chars |
| `version` | string | yes | 1–128 chars |
| `actuator_type` | string | yes | `coding` \| `decoding` |
| `requirements` | string[] | yes | `[]` if none |
| `method` | string | yes | Source code |
| `method_args` | object | no | |
| `set_latest` | bool | no | Default `false` |

Rules:
1. Same `name` + `version` already active → `400`.
2. First active actuator of a name always becomes latest, even with `set_latest: false`.
3. `set_latest: true` → previous latest loses its flag.

`201` actuator · `400` duplicate · `422` invalid body.

### PUT /actuators/{actuator_id}

No body. Makes this actuator the latest of its name; the previous latest loses the flag. Used for promotion and rollback.

`200` actuator with `latest: true` · `400` already latest · `404` not found.

### DELETE /actuators/{actuator_id}

Cannot delete the latest version. To remove it: promote another version with `PUT`, then delete.

`204` · `404` not found · `409` it is the latest version.

---

## Data

The output of an actuator as the link carries or uses it (embedding, quantized indices, compressed payload...).

| Method | Path | Purpose |
|---|---|---|
| GET | `/data` | List |
| GET | `/data/{data_id}` | Get one |
| POST | `/data` | Create |
| PUT | `/data/{data_id}` | Change `linked_resource` and/or `specs` |
| DELETE | `/data/{data_id}` | Soft delete |

### Data object

| Field | Type | Notes |
|---|---|---|
| `id` | string | ID |
| `actuator_id` | string | Actuator that produced it |
| `metadata` | any JSON | The actuator output |
| `linked_resource` | string \| null | Reference to the original input (e.g. a content `identifier` or `id`). Not validated. |
| `specs` | object \| null | Free-form (channel, SNR, CBR, metrics...) |
| `created_at`, `updated_at` | string | UTC |

### GET /data

Extra query param: `actuator_id` (string, optional) — only items made by that actuator. There is no specs filter on data.

Response `200`: `{"total": N, "data": [ ... ]}`

### GET /data/{data_id}

Query param `metadata_only` (bool, default `false`). When `true` the response is only `{"id", "actuator_id", "metadata"}` — use it on receivers that only need the payload.

`200` data · `404` not found.

### POST /data

| Field | Type | Required | Notes |
|---|---|---|---|
| `actuator_id` | string | yes | Must be the **latest** active version |
| `metadata` | any JSON | yes | |
| `linked_resource` | string \| null | yes | Send `null` explicitly if none |
| `specs` | object \| null | yes | Send `null` explicitly if none |

`201` data · `404` actuator missing **or not the latest version** · `422` invalid body (often a missing `linked_resource`/`specs` key).

### PUT /data/{data_id}

| Field | Type | Required | Notes |
|---|---|---|---|
| `linked_resource` | string \| null | no | |
| `specs` | object \| null | no | **Replaces** the whole stored specs object |

- Missing or `null` field → unchanged. Therefore a field cannot be cleared to `null` with this endpoint.
- `actuator_id` and `metadata` are immutable; create a new data item for a new output.
- To change one specs key: GET, merge locally, PUT the full object.

`200` data · `404` not found.

### DELETE /data/{data_id}

`204` · `404` not found.

---

## Contents

The original input, kept for evaluation, retraining or audit.

| Method | Path | Purpose |
|---|---|---|
| GET | `/contents` | List, optional specs filter |
| GET | `/contents/{content_id}` | Get one |
| POST | `/contents` | Create |
| PUT | `/contents/{content_id}/specs` | Merge specs keys |
| DELETE | `/contents/{content_id}` | Soft delete |

### Content object

| Field | Type | Notes |
|---|---|---|
| `id` | string | ID |
| `identifier` | string | Identifier of the original input. Not unique — the server does not check. |
| `specs` | object \| null | Free-form (modality, format, storage location, the text itself...) |
| `created_at`, `updated_at` | string | UTC |

### GET /contents

Extra query param: `specs` — a JSON object **encoded as a string**; every key must equal its value (exact match). URL-encode it:

```bash
curl -G "$NEXGEN_URL/api/v1/contents" -H "X-API-Key: $NEXGEN_API_KEY" \
  --data-urlencode 'specs={"modality": "text"}'
```

Response `200`: `{"total": N, "data": [ ... ]}` — note the key is **`data`**, not `contents`.

`422` if `specs` is not a valid JSON object. There is no filter on `identifier`; to look up by identifier, also store it in specs (e.g. `specs.identifier`) and filter on that.

### GET /contents/{content_id}

`200` content · `404` not found.

### POST /contents

| Field | Type | Required | Notes |
|---|---|---|---|
| `identifier` | string | yes | |
| `specs` | object \| null | yes | Send `null` explicitly if none |

`201` content · `422` invalid body.

### PUT /contents/{content_id}/specs

Body: `{"specs": {...}}` (required). **Merges** into the stored specs: existing keys get new values, new keys are added, other keys untouched. (Opposite of `PUT /data/{id}`, which replaces.)

Example: stored `{"modality": "text", "language": "en"}` + body `{"specs": {"language": "tr", "split": "test"}}` → `{"modality": "text", "language": "tr", "split": "test"}`.

`200` content · `404` not found · `422` invalid body.

### DELETE /contents/{content_id}

Data items that reference the content are not changed. `204` · `404` not found.

---

## Health

Public — no API key needed.

| Method | Path | Response |
|---|---|---|
| GET | `/health` | `200 {"status": "ok"}` — process is up |
| GET | `/health/ready` | `200 {"status": "ready"}` — MongoDB reachable; server error otherwise |

---

## Errors

All errors are JSON with a `detail` key: `{"detail": "Actuator '6650...' not found"}`. For `422`, `detail` is a list of the failing fields.

| Status | Meaning |
|---|---|
| 400 | Already exists: duplicate name+version, or promoting an actuator that is already latest |
| 401 | API key missing or wrong |
| 404 | No active item with that ID/name; invalid ObjectId; or data created from a non-latest actuator |
| 409 | Tried to delete the latest version of an actuator |
| 422 | Invalid body or query parameter |

---

## Code examples

For Python applications the project's own client is [nexgenpy](https://github.com/iamalreadynoob/nexgen). Check its README for its interface before using it. With plain HTTP:

```python
import os
import requests

BASE = os.environ.get("NEXGEN_URL", "http://localhost:8000").rstrip("/") + "/api/v1"
session = requests.Session()
if key := os.environ.get("NEXGEN_API_KEY"):
    session.headers["X-API-Key"] = key


def call(method: str, path: str, **kwargs):
    resp = session.request(method, BASE + path, timeout=30, **kwargs)
    if resp.status_code >= 400:
        raise RuntimeError(f"{method} {path} -> {resp.status_code}: {resp.json().get('detail')}")
    return resp.json() if resp.content else None


# Transmitter: fetch latest coding actuator, store content and data
encoder = call("GET", "/actuators/text-embedder/latest")
content = call("POST", "/contents", json={"identifier": "sentence-0001",
                                          "specs": {"modality": "text", "identifier": "sentence-0001"}})
vector = [0.12, -0.53, 0.98]  # result of running encoder["method"] in a sandbox
item = call("POST", "/data", json={"actuator_id": encoder["_id"], "metadata": vector,
                                   "linked_resource": content["id"],
                                   "specs": {"channel": "AWGN", "snr_db": 10}})

# Receiver: read payload, fetch matching decoder
payload = call("GET", f"/data/{item['id']}", params={"metadata_only": "true"})
decoder = call("GET", "/actuators/text-decoder/latest")

# Contents filter: specs must be a JSON string
import json
texts = call("GET", "/contents", params={"specs": json.dumps({"modality": "text"})})["data"]
```

Paginate everything:

```python
def list_all(resource: str, key: str, **params):
    page, items = 1, []
    while True:
        body = call("GET", f"/{resource}", params={**params, "page": page, "limit": 100})
        items += body[key]
        if not body[key] or len(items) >= body["total"]:
            return items
        page += 1

actuators = list_all("actuators", "actuators", latest="true")
contents = list_all("contents", "data")  # contents use the "data" key
```
