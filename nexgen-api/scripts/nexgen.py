#!/usr/bin/env python3
"""Command-line client for the Nexgen Server REST API (standard library only).

Configuration (environment variables):
    NEXGEN_URL      Server root, default http://localhost:8000 (``/api/v1`` is appended)
    NEXGEN_API_KEY  Value for the X-API-Key header (omit if auth is off)

Every command prints the JSON response to stdout. On an HTTP error it prints
``HTTP <status>: <detail>`` to stderr and exits with code 1.

Arguments that take JSON accept a literal (``'{"a": 1}'``) or ``@path/to/file.json``.

Examples:
    nexgen.py health --ready
    nexgen.py actuators latest text-embedder --save-method encoder.py
    nexgen.py actuators create --name text-embedder --version 1.1.0 --type coding \
        --requirements numpy==2.1.0 --method @encoder.py --set-latest
    nexgen.py actuators promote 6650c0ffee0000000000abcd
    nexgen.py data create --actuator-name text-embedder --metadata '[0.1, 0.2]' \
        --linked-resource sentence-0001 --specs '{"channel": "AWGN", "snr_db": 10}'
    nexgen.py contents list --specs '{"modality": "text"}' --all
    nexgen.py raw GET /actuators --query latest=true
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

API_PREFIX = "/api/v1"
# Key that holds the items in each list response. Contents use "data", not "contents".
LIST_KEYS = {"actuators": "actuators", "data": "data", "contents": "data"}


class ApiError(Exception):
    def __init__(self, status: int, detail: Any) -> None:
        super().__init__(f"HTTP {status}: {detail}")
        self.status = status
        self.detail = detail


def base_url() -> str:
    return os.environ.get("NEXGEN_URL", "http://localhost:8000").rstrip("/") + API_PREFIX


def request(method: str, path: str, query: dict | None = None, body: Any = None) -> Any:
    """Send one request and return the decoded JSON body (None for 204)."""
    url = base_url() + path
    if query:
        clean = {k: _query_value(v) for k, v in query.items() if v is not None}
        if clean:
            url += "?" + urllib.parse.urlencode(clean)
    headers = {"Accept": "application/json"}
    api_key = os.environ.get("NEXGEN_API_KEY")
    if api_key:
        headers["X-API-Key"] = api_key
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            detail = json.loads(raw).get("detail", raw.decode())
        except (ValueError, AttributeError):
            detail = raw.decode(errors="replace")
        raise ApiError(exc.code, detail) from None
    except urllib.error.URLError as exc:
        raise ApiError(0, f"cannot reach {url}: {exc.reason}") from None
    return json.loads(raw) if raw else None


def _query_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    return str(value)


def list_items(resource: str, query: dict, fetch_all: bool) -> dict:
    """Get one page, or every page when fetch_all is set."""
    key = LIST_KEYS[resource]
    if not fetch_all:
        return request("GET", f"/{resource}", query=query)
    query = {**query, "page": 1, "limit": query.get("limit") or 100}
    items: list = []
    while True:
        page = request("GET", f"/{resource}", query=query)
        items.extend(page[key])
        if not page[key] or len(items) >= page["total"]:
            return {"total": page["total"], key: items}
        query["page"] += 1


def load_json(value: str | None) -> Any:
    """Parse a JSON literal or @file argument."""
    if value is None:
        return None
    if value.startswith("@"):
        with open(value[1:], encoding="utf-8") as fh:
            return json.load(fh)
    return json.loads(value)


def load_text(value: str) -> str:
    """Return a literal string or the contents of an @file argument."""
    if value.startswith("@"):
        with open(value[1:], encoding="utf-8") as fh:
            return fh.read()
    return value


def parse_bool(value: str) -> bool:
    lowered = value.lower()
    if lowered in ("true", "1", "yes"):
        return True
    if lowered in ("false", "0", "no"):
        return False
    raise argparse.ArgumentTypeError(f"expected true or false, got {value!r}")


def latest_actuator_id(name: str) -> str:
    return request("GET", f"/actuators/{urllib.parse.quote(name, safe='')}/latest")["_id"]


# --- command handlers -------------------------------------------------------


def cmd_health(args: argparse.Namespace) -> Any:
    return request("GET", "/health/ready" if args.ready else "/health")


def cmd_actuators(args: argparse.Namespace) -> Any:
    if args.action == "list":
        query = {"page": args.page, "limit": args.limit, "ascending": args.ascending, "latest": args.latest}
        return list_items("actuators", query, args.all)
    if args.action == "get":
        return request("GET", f"/actuators/{args.id}")
    if args.action == "latest":
        actuator = request("GET", f"/actuators/{urllib.parse.quote(args.name, safe='')}/latest")
        if args.save_method:
            with open(args.save_method, "w", encoding="utf-8") as fh:
                fh.write(actuator["method"])
            print(f"method written to {args.save_method}", file=sys.stderr)
        return actuator
    if args.action == "create":
        body = {
            "name": args.name,
            "version": args.version,
            "actuator_type": args.type,
            "requirements": [r.strip() for r in args.requirements.split(",") if r.strip()] if args.requirements else [],
            "method": load_text(args.method),
            "set_latest": args.set_latest,
        }
        if args.method_args:
            body["method_args"] = load_json(args.method_args)
        return request("POST", "/actuators", body=body)
    if args.action == "promote":
        return request("PUT", f"/actuators/{args.id}")
    if args.action == "delete":
        request("DELETE", f"/actuators/{args.id}")
        return {"deleted": args.id}
    raise AssertionError(args.action)


def cmd_data(args: argparse.Namespace) -> Any:
    if args.action == "list":
        query = {"page": args.page, "limit": args.limit, "ascending": args.ascending, "actuator_id": args.actuator_id}
        return list_items("data", query, args.all)
    if args.action == "get":
        return request("GET", f"/data/{args.id}", query={"metadata_only": args.metadata_only or None})
    if args.action == "create":
        actuator_id = args.actuator_id or latest_actuator_id(args.actuator_name)
        body = {
            "actuator_id": actuator_id,
            "metadata": load_json(args.metadata),
            "linked_resource": args.linked_resource,
            "specs": load_json(args.specs),
        }
        return request("POST", "/data", body=body)
    if args.action == "update":
        body = {}
        if args.linked_resource is not None:
            body["linked_resource"] = args.linked_resource
        if args.specs is not None:
            body["specs"] = load_json(args.specs)
        if args.merge_specs is not None:
            current = request("GET", f"/data/{args.id}").get("specs") or {}
            body["specs"] = {**current, **load_json(args.merge_specs)}
        if not body:
            raise SystemExit("nothing to update: pass --linked-resource, --specs or --merge-specs")
        return request("PUT", f"/data/{args.id}", body=body)
    if args.action == "delete":
        request("DELETE", f"/data/{args.id}")
        return {"deleted": args.id}
    raise AssertionError(args.action)


def cmd_contents(args: argparse.Namespace) -> Any:
    if args.action == "list":
        query = {"page": args.page, "limit": args.limit, "ascending": args.ascending}
        if args.specs:
            query["specs"] = load_json(args.specs)
        return list_items("contents", query, args.all)
    if args.action == "get":
        return request("GET", f"/contents/{args.id}")
    if args.action == "create":
        return request("POST", "/contents", body={"identifier": args.identifier, "specs": load_json(args.specs)})
    if args.action == "merge-specs":
        return request("PUT", f"/contents/{args.id}/specs", body={"specs": load_json(args.specs)})
    if args.action == "delete":
        request("DELETE", f"/contents/{args.id}")
        return {"deleted": args.id}
    raise AssertionError(args.action)


def cmd_raw(args: argparse.Namespace) -> Any:
    query = dict(pair.split("=", 1) for pair in args.query)
    path = args.path if args.path.startswith("/") else "/" + args.path
    return request(args.method.upper(), path, query=query, body=load_json(args.body))


# --- argument parsing -------------------------------------------------------


def add_paging(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--page", type=int)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--ascending", action="store_true", default=None, help="oldest first")
    parser.add_argument("--all", action="store_true", help="follow pages until every item is fetched")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="resource", required=True)

    health = sub.add_parser("health", help="liveness / readiness probe")
    health.add_argument("--ready", action="store_true", help="check MongoDB too")
    health.set_defaults(func=cmd_health)

    act = sub.add_parser("actuators", help="versioned coding/decoding methods")
    act.set_defaults(func=cmd_actuators)
    act_sub = act.add_subparsers(dest="action", required=True)
    p = act_sub.add_parser("list")
    add_paging(p)
    p.add_argument("--latest", type=parse_bool, help="true: only latest versions; false: only non-latest")
    act_sub.add_parser("get").add_argument("id")
    p = act_sub.add_parser("latest")
    p.add_argument("name")
    p.add_argument("--save-method", metavar="FILE", help="write the method source to FILE")
    p = act_sub.add_parser("create")
    p.add_argument("--name", required=True)
    p.add_argument("--version", required=True)
    p.add_argument("--type", required=True, choices=["coding", "decoding"])
    p.add_argument("--requirements", default="", help="comma-separated packages, e.g. numpy==2.1.0,torch")
    p.add_argument("--method", required=True, help="source code, or @file.py")
    p.add_argument("--method-args", help='JSON, e.g. {"text": {"type": "str"}}')
    p.add_argument("--set-latest", action="store_true")
    act_sub.add_parser("promote", help="mark as latest (also used to roll back)").add_argument("id")
    act_sub.add_parser("delete", help="soft delete; fails with 409 on the latest").add_argument("id")

    data = sub.add_parser("data", help="actuator outputs")
    data.set_defaults(func=cmd_data)
    data_sub = data.add_subparsers(dest="action", required=True)
    p = data_sub.add_parser("list")
    add_paging(p)
    p.add_argument("--actuator-id")
    p = data_sub.add_parser("get")
    p.add_argument("id")
    p.add_argument("--metadata-only", action="store_true")
    p = data_sub.add_parser("create")
    who = p.add_mutually_exclusive_group(required=True)
    who.add_argument("--actuator-id")
    who.add_argument("--actuator-name", help="resolve the latest version of this name")
    p.add_argument("--metadata", required=True, help="JSON value, or @file.json")
    p.add_argument("--linked-resource")
    p.add_argument("--specs", help="JSON object, or @file.json")
    p = data_sub.add_parser("update")
    p.add_argument("id")
    p.add_argument("--linked-resource")
    specs = p.add_mutually_exclusive_group()
    specs.add_argument("--specs", help="replaces the whole specs object")
    specs.add_argument("--merge-specs", help="read current specs, merge these keys, then PUT")
    data_sub.add_parser("delete").add_argument("id")

    cont = sub.add_parser("contents", help="original inputs")
    cont.set_defaults(func=cmd_contents)
    cont_sub = cont.add_subparsers(dest="action", required=True)
    p = cont_sub.add_parser("list")
    add_paging(p)
    p.add_argument("--specs", help='exact-match filter, e.g. {"modality": "text"}')
    cont_sub.add_parser("get").add_argument("id")
    p = cont_sub.add_parser("create")
    p.add_argument("--identifier", required=True)
    p.add_argument("--specs", help="JSON object, or @file.json")
    p = cont_sub.add_parser("merge-specs", help="server-side merge of specs keys")
    p.add_argument("id")
    p.add_argument("--specs", required=True)
    cont_sub.add_parser("delete").add_argument("id")

    raw = sub.add_parser("raw", help="any request, e.g. raw GET /actuators --query latest=true")
    raw.add_argument("method")
    raw.add_argument("path", help="path below /api/v1")
    raw.add_argument("--query", action="append", default=[], metavar="KEY=VALUE")
    raw.add_argument("--body", help="JSON body, or @file.json")
    raw.set_defaults(func=cmd_raw)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = args.func(args)
    except ApiError as exc:
        print(exc, file=sys.stderr)
        return 1
    except (ValueError, OSError) as exc:
        print(f"bad argument: {exc}", file=sys.stderr)
        return 2
    if result is not None:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
