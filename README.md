# Nexgen Server Skill

This repository contains `nexgen-api`, an [Agent Skill](https://docs.claude.com/en/docs/claude-code/skills) that teaches Claude how to use the [Nexgen Server](https://github.com/iamalreadynoob/nexgen-server) REST API.

With the skill installed, you can ask Claude to do API tasks in plain language, for example "publish version 1.2.0 of my text-embedder" or "why does my POST /data return 404?". Claude then knows the endpoints, the actuator version rules and the common mistakes. It also has a ready-made command-line client to run the requests.

## Repository contents

```text
nexgen-server-skill/
├── README.md                       # This file
├── nexgen-api/                     # The skill. Install this folder.
│   ├── SKILL.md                    # Instructions that Claude reads when the skill activates
│   ├── references/
│   │   └── api-reference.md        # All endpoints, fields, rules and errors
│   └── scripts/
│       └── nexgen.py               # Command-line client for all endpoints
└── nexgen-server-docs/             # The Nexgen Server documentation that the skill is based on
```

## What the skill helps with

- **Actuators:** register new versions, promote a version or roll back, retire old versions, and download an actuator's code to run in a sandbox.
- **Data:** post actuator outputs from the latest version, read payloads with `metadata_only`, and update specs without losing keys.
- **Contents:** store original inputs, filter them by specs, and merge specs keys.
- **Health:** check that the server and MongoDB respond.
- **Client code:** write transmitter or receiver code in Python (plain HTTP or [nexgenpy](https://github.com/iamalreadynoob/nexgen)) or in other languages.
- **Debugging:** explain what a `400`, `401`, `404`, `409` or `422` response means and how to fix it.

## Requirements

- Claude Code, or another Claude app that supports custom skills
- Python 3.8 or later, for the bundled client. It uses only the standard library.
- Network access from your machine to a running Nexgen Server

## Installation

Clone the repository:

```bash
git clone https://github.com/iamalreadynoob/nexgen-server-skill.git
cd nexgen-server-skill
```

Then copy or link the `nexgen-api` folder into a skills directory.

**For your user account** (all your projects):

```bash
mkdir -p ~/.claude/skills
cp -r nexgen-api ~/.claude/skills/
# or, to get updates automatically: ln -s "$(pwd)/nexgen-api" ~/.claude/skills/nexgen-api
```

**For one project** (shared with everyone who clones it). Run this in the root of that project, with the path to your clone:

```bash
mkdir -p .claude/skills
cp -r /path/to/nexgen-server-skill/nexgen-api .claude/skills/
```

Start a new Claude Code session. To check the installation, run `/skills` or ask "which skills do you have?". The list should show `nexgen-api`.

For Claude apps that accept skill uploads, compress the `nexgen-api` folder into a ZIP file and upload it in the skill settings. The bundled client can only reach servers that the app's environment can connect to.

## Configuration

The skill reads two environment variables:

| Variable | Default | Description |
|---|---|---|
| `NEXGEN_URL` | `http://localhost:8000` | The server root. The client adds `/api/v1`. |
| `NEXGEN_API_KEY` | not set | The value of the `X-API-Key` header. Do not set it if the server runs without authentication. |

Set them before you start Claude:

```bash
export NEXGEN_URL=https://nexgen.example.com
export NEXGEN_API_KEY=<your-key>
```

If you do not set them, Claude asks you for the URL and the key.

> [!WARNING]
> Each valid API key can read, change and delete all items on the server. Do not put your key in files that you commit.

## Example prompts

```text
Is the Nexgen server on localhost up?
Register encoder.py as version 2.0.0 of "image-jscc", a coding actuator that needs torch==2.4.0. Don't make it latest yet.
Promote image-jscc 2.0.0, and roll back to 1.3.0 if I tell you so.
Delete all versions of text-embedder except the latest one.
Show me all text contents with split=test.
Add psnr=31.2 and ssim=0.94 to the specs of data item 6650c0ffee0000000000d001.
Write a Python receiver that gets the newest data items of image-jscc, gets the decoder and stores the PSNR back.
My POST /api/v1/data returns 404 but the actuator exists. Why?
```

## Using the client without Claude

You can also run the bundled client yourself:

```bash
nx() { python3 nexgen-api/scripts/nexgen.py "$@"; }

nx health --ready
nx actuators list --latest true --all
nx actuators latest text-embedder --save-method encoder.py
nx actuators create --name text-embedder --version 1.1.0 --type coding \
   --requirements numpy==2.1.0 --method @encoder.py --set-latest
nx actuators promote <actuator_id>
nx data create --actuator-name text-embedder --metadata '[0.12, -0.53]' \
   --linked-resource <content_id> --specs '{"channel": "AWGN", "snr_db": 10}'
nx data update <data_id> --merge-specs '{"psnr": 31.2}'
nx contents list --specs '{"modality": "text"}' --all
nx raw GET /actuators --query latest=false
```

- Options that take JSON accept a literal value or `@file.json`. `--method` also accepts `@file.py`.
- `--actuator-name` uses the current latest version of that actuator name. The server accepts new data only from the latest version.
- `--merge-specs` gets the data item, merges the keys and sends the full specs object. The data endpoint replaces specs; it does not merge them.
- `--all` gets all the pages of a list. The default page size of the server is 10.
- The client writes the response JSON to stdout. On an HTTP error, it writes `HTTP <status>: <detail>` to stderr and exits with code 1.

Run `python3 nexgen-api/scripts/nexgen.py <resource> <action> -h` to see all options.

## Safety

- **Actuator code is untrusted.** Any user with a valid key can store code on the server. The skill tells Claude to show you the code first, and to run it only in a container, a sandbox or a separate virtual environment.
- **The latest flag affects all clients.** Promote, roll back, create with `--set-latest` and delete change the actuator that all transmitters and receivers use. On a shared server, Claude asks you before it does these operations.
- **Data items can contain private information.** An embedding can show its original content. Protect data items like the content.

## Updating the skill

When the Nexgen Server API changes, update `nexgen-server-docs/` first. Then update these files in `nexgen-api/`:

1. `references/api-reference.md`: the endpoint details
2. `scripts/nexgen.py`: the commands for new or changed endpoints
3. `SKILL.md`: the rules and workflows, if the behavior changes. Also update the `description` field if the skill must activate for new topics.

If you installed the skill with `cp`, copy the folder again after an update. A symbolic link gets the changes automatically.
