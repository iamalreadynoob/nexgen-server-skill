---
name: nexgen-api
description: Work with the Nexgen Server REST API, a FastAPI + MongoDB registry for semantic communication (SemCom) apps that stores versioned actuators (coding/decoding Python methods), data items (actuator outputs) and content items (original inputs) under /api/v1. Use this skill whenever the user wants to call, script, test, debug or write client code for Nexgen Server. That covers registering, promoting, rolling back or deleting actuator versions, getting the latest actuator, posting or reading data items and embeddings, storing or filtering contents by specs, checking health, or reading Nexgen API errors (400/401/404/409/422). Also use it when the user mentions nexgen, nexgenpy, actuators with `set_latest`, `linked_resource`, or a transmitter/receiver pipeline backed by this server, even if they never say "API".
---

# Nexgen Server API

Nexgen Server is the shared registry and data store between a SemCom transmitter and receiver. It does **not** run code. It stores three things:

| Resource | What it is | ID key |
|---|---|---|
| **Actuator** | A versioned, named Python method (`coding` or `decoding`) with its `requirements` | `_id` |
| **Data** | The output of an actuator (e.g. an embedding), tied to `actuator_id` | `id` |
| **Content** | The original input (`identifier` + free-form `specs`) | `id` |

The full field and endpoint reference is in [references/api-reference.md](references/api-reference.md). Read the section you need before you build a request body you have not used before.

## Setup

1. Find the server URL and API key. Ask the user, or look for them in the environment, a `.env` file, or the project config. Default URL: `http://localhost:8000`. All paths are under `/api/v1`.
2. Export them for the bundled client:
   ```bash
   export NEXGEN_URL=http://localhost:8000
   export NEXGEN_API_KEY=...        # leave unset if the server runs without auth
   ```
3. Check that the server is up: `python3 scripts/nexgen.py health --ready` (health needs no key).

Treat the API key as a secret. Do not echo it, write it into committed files, or paste it into chat output. Every valid key has full read/write/delete access.

## The bundled client

`scripts/nexgen.py` (path relative to this skill) is a standard-library-only CLI that covers every endpoint. It prints JSON and exits non-zero on errors with `HTTP <status>: <detail>`. Prefer it over hand-written curl, because it handles the auth header, JSON encoding of the `specs` filter, sending explicit `null`s, and pagination. Run `python3 scripts/nexgen.py <resource> <action> -h` for the options.

```bash
nx() { python3 <skill-dir>/scripts/nexgen.py "$@"; }   # a function works in bash and zsh
nx actuators list --latest true --all
nx actuators latest text-embedder --save-method /tmp/encoder.py
nx actuators create --name text-embedder --version 1.1.0 --type coding \
   --requirements numpy==2.1.0 --method @encoder.py --method-args @args.json --set-latest
nx actuators promote <actuator_id>         # also the rollback command
nx actuators delete <actuator_id>
nx data create --actuator-name text-embedder --metadata @vec.json \
   --linked-resource <content_id> --specs '{"channel":"AWGN","snr_db":10}'
nx data get <data_id> --metadata-only
nx data update <data_id> --merge-specs '{"psnr": 31.2}'
nx contents create --identifier img-0042 --specs '{"modality":"image","identifier":"img-0042"}'
nx contents list --specs '{"modality":"image"}' --all
nx contents merge-specs <content_id> --specs '{"split":"test"}'
nx raw GET /actuators --query latest=false   # escape hatch
```

JSON options accept a literal or `@file`. `--actuator-name` looks up the current latest version, which avoids the most common data-creation error (see below).

When the user is writing their own application code instead, write the code for them. In Python, mention the [nexgenpy](https://github.com/iamalreadynoob/nexgen) client. Check its interface first instead of guessing. Otherwise use plain HTTP; the reference file has a `requests` example.

## Rules that surprise people

These cause most failed calls. Keep them in mind when you build requests and when you explain errors.

1. **Data must come from the latest actuator.** `POST /data` with an old version's `actuator_id` returns **404**, not 400. A 404 here usually means someone promoted a new version. Get `/actuators/{name}/latest` again, run that version, then post.
2. **`POST /data` and `POST /contents` need every field.** Send `linked_resource: null` / `specs: null` explicitly. If you leave them out, you get 422.
3. **Specs updates are different for each resource.** `PUT /data/{id}` *replaces* the whole `specs` object. `PUT /contents/{id}/specs` *merges* keys. To change one key on a data item, GET it, merge locally, then PUT (or use `data update --merge-specs`).
4. **`PUT /data/{id}` cannot clear a field.** A field that is missing or `null` stays unchanged. `actuator_id` and `metadata` cannot change; create a new data item.
5. **Latest-flag lifecycle:**
   - The first actuator of a name becomes latest automatically, even with `set_latest: false`.
   - `set_latest: true` on create, or `PUT /actuators/{id}`, takes the flag from the old latest.
   - Promoting the current latest → 400.
   - Deleting the latest → 409. Promote another version first, then delete.
   - Same name + version as an active actuator → 400. After a soft delete, that pair can be used again.
6. **ID key names differ.** Actuators return `_id`; data and contents return `id`. An invalid ObjectId gives 404, not 422.
7. **List response keys:** actuators → `actuators`; data → `data`; **contents → `data` too**. The default page size is 10, newest first. Use `--all` (or loop on `total`) when the user wants everything.
8. **Filtering is limited.** Data can be filtered only by `actuator_id`. Contents can be filtered only by exact-match `specs`, sent as a URL-encoded JSON string. Nothing filters on `identifier`, and `identifier` is not unique. If you need to find content again later, put the identifier in `specs` too, or store the content `id` in the data item's `linked_resource` so that a direct GET works.
9. **Deletes are soft.** The item disappears from all responses. Deleting content does not change the data items that refer to it.

## Common workflows

### Publish a new actuator version

1. `actuators latest <name>` to see the current version and `actuator_type`.
2. Choose a new `version` string. Keep the existing scheme (semver if they use it).
3. Decide on rollout:
   - **Immediate:** create with `--set-latest`.
   - **Staged:** create without it, review or test, then `actuators promote <new_id>`.
4. Pin versions in `requirements` (e.g. `numpy==2.1.0`). The receiver installs exactly these.
5. If the method loads model weights or a codebook, a change to them needs a new version too. Otherwise the transmitter and receiver quietly disagree.

### Roll back

`actuators list --latest false --all`, find the previous version of the name, then `actuators promote <old_id>`. Every client that asks for latest gets the old version from now on.

### Retire old versions

Delete only non-latest IDs. If the user wants to delete the current latest, promote the replacement first. Otherwise the call fails with 409.

### Transmitter side

1. Get the latest `coding` actuator. Save `method` to a file and run it in an isolated environment with `requirements` installed (see Safety).
2. `POST /contents` for the original input (optional, but needed for evaluation or retraining later).
3. `POST /data` with the latest actuator's `_id`, the output as `metadata`, a `linked_resource` back to the content, and link details in `specs`.

### Receiver side

1. `GET /data/{id}?metadata_only=true` (or `data list --actuator-id <id>`).
2. Get the latest `decoding` actuator of the paired name and run it on `metadata`.
3. For evaluation, load the original content (via `linked_resource`) and compare it with the reconstruction. Store the scores back with `data update --merge-specs`.

### Suggested `specs` keys

Specs are free-form. Results are only comparable when they record the same things. Suggest consistent keys such as `modality`, `channel` (`AWGN`, `Rayleigh`...), `snr_db`, `cbr`, `metric`/score keys (`psnr`, `ssim`, `lpips`, `bleu`, `sbert_cosine`, `accuracy`), `baseline`, and `split`. For generative decoders, also record a semantic-consistency score (CLIP score, sentence similarity), because perceptual metrics alone miss hallucinations.

## Reading errors

Errors are `{"detail": ...}`. When a call fails, tell the user what it means here, not only the status code:

| Status | Likely cause → fix |
|---|---|
| 401 | Key missing or wrong → check `NEXGEN_API_KEY` |
| 400 | Duplicate name+version → bump the version. Or the actuator is already latest → nothing to do |
| 404 on `POST /data` | Actuator is not the latest → get latest again and retry with its `_id` |
| 404 elsewhere | Wrong, deleted or malformed ID → list to find the right one |
| 409 | Deleting the latest → promote another version first |
| 422 | Body or query is malformed. `detail` lists the fields. Often missing `null`s or a bad `specs` JSON string |

## Safety

- **Actuator code is untrusted.** Any key holder can store a `method`. Before you run one, show the user the source. Run it in a container, a sandbox or a separate venv without secrets. Do not install its `requirements` into the user's main environment, and do not `exec` it in the agent's own process.
- **Changing the latest flag affects every client.** Promote, roll back, create with `--set-latest`, and delete all change what transmitters and receivers use or see. On a shared or production server, confirm with the user before you do these. Read-only calls need no confirmation.
- Data items (such as embeddings) can leak the original content. Handle them as carefully as the content.
