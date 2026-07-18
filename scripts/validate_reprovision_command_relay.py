#!/usr/bin/env python3
"""Validate reprovision + command relay flows against a Unit Connector site.

Usage example:
  python3 scripts/validate_reprovision_command_relay.py \
    --uc-url https://example.com \
    --unit-id 123456 \
    --admin-key YOUR_X_TMON_ADMIN_KEY

What this script validates:
1) Reprovision surrogate: POST staged settings to /wp-json/tmon/v1/admin/device/settings.
2) Command enqueue: POST command to /wp-json/tmon-uc/v1/device/command.
3) Device poll: POST /wp-json/tmon/v1/device/commands and assert command appears.
4) Result post: POST /wp-json/tmon/v1/device/command-result.
5) Re-poll: ensure completed command no longer appears as queued/claimed.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass
class HttpResult:
    status: int
    body: Any
    raw: str


class FlowError(RuntimeError):
    pass


def _normalize_base(url: str) -> str:
    return url.rstrip("/")


def _request_json(
    method: str,
    url: str,
    payload: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 20,
) -> HttpResult:
    data_bytes = None
    req_headers: Dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "TMON-FlowValidator/1.0",
    }
    if payload is not None:
        data_bytes = json.dumps(payload).encode("utf-8")
        req_headers["Content-Type"] = "application/json"
    if headers:
        req_headers.update(headers)

    req = Request(url=url, data=data_bytes, headers=req_headers, method=method.upper())
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            status = int(resp.status)
    except HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        status = int(e.code)
    except URLError as e:
        raise FlowError(f"Request failed for {url}: {e}") from e

    body: Any
    try:
        body = json.loads(raw) if raw.strip() else {}
    except Exception:
        body = {"_non_json": raw}

    return HttpResult(status=status, body=body, raw=raw)


def _assert_status(name: str, got: int, allowed: List[int]) -> None:
    if got not in allowed:
        raise FlowError(f"{name} unexpected status {got}; expected one of {allowed}")


def _print_step(step: str, detail: str) -> None:
    print(f"[STEP] {step}: {detail}")


def run_validation(
    uc_url: str,
    unit_id: str,
    admin_key: str,
    command_type: str,
    command_key: str,
    command_value: str,
    poll_retries: int,
    poll_delay_s: float,
) -> None:
    base = _normalize_base(uc_url)

    settings_endpoint = f"{base}/wp-json/tmon/v1/admin/device/settings"
    enqueue_endpoint = f"{base}/wp-json/tmon-uc/v1/device/command"
    poll_endpoint = f"{base}/wp-json/tmon/v1/device/commands"
    result_endpoint = f"{base}/wp-json/tmon/v1/device/command-result"

    staged_payload = {
        "unit_id": unit_id,
        "settings": {
            command_key: command_value,
            "_flow_validation_ts": int(time.time()),
        },
    }

    _print_step("1/5 reprovision", "staging settings to Unit Connector admin endpoint")
    reprovision = _request_json(
        "POST",
        settings_endpoint,
        payload=staged_payload,
        headers={"X-TMON-ADMIN": admin_key},
    )
    _assert_status("reprovision", reprovision.status, [200, 201])
    if isinstance(reprovision.body, dict) and reprovision.body.get("status") not in (None, "ok"):
        raise FlowError(f"reprovision endpoint returned non-ok body: {reprovision.body}")

    cmd_payload = {
        "unit_id": unit_id,
        "type": command_type,
        "data": {
            "key": command_key,
            "value": command_value,
            "source": "validate_reprovision_command_relay.py",
        },
    }

    _print_step("2/5 command enqueue", "queueing command for target unit")
    enqueue = _request_json("POST", enqueue_endpoint, payload=cmd_payload)
    _assert_status("command enqueue", enqueue.status, [200, 201])

    _print_step("3/5 command poll", "polling command queue until command appears")
    command_id: Optional[int] = None
    for _ in range(max(1, poll_retries)):
        polled = _request_json("POST", poll_endpoint, payload={"unit_id": unit_id})
        _assert_status("command poll", polled.status, [200, 201])

        commands: List[Dict[str, Any]] = []
        if isinstance(polled.body, list):
            commands = [c for c in polled.body if isinstance(c, dict)]
        elif isinstance(polled.body, dict):
            c = polled.body.get("commands")
            if isinstance(c, list):
                commands = [x for x in c if isinstance(x, dict)]

        for cmd in commands:
            ctype = str(cmd.get("type") or cmd.get("command") or "").strip().lower()
            if ctype == command_type.lower() and cmd.get("id") is not None:
                try:
                    command_id = int(cmd.get("id"))
                except Exception:
                    command_id = None
                break

        if command_id is not None:
            break
        time.sleep(max(0.0, poll_delay_s))

    if command_id is None:
        raise FlowError("queued command was not observed via device poll endpoint")

    _print_step("4/5 command result", f"posting completion for command id {command_id}")
    result = _request_json(
        "POST",
        result_endpoint,
        payload={
            "id": command_id,
            "status": "done",
            "result": {"ok": True, "validator": "flow-script"},
        },
    )
    _assert_status("command result", result.status, [200, 201])

    _print_step("5/5 queue verify", "re-polling queue to verify command is no longer pending")
    final_poll = _request_json("POST", poll_endpoint, payload={"unit_id": unit_id})
    _assert_status("final command poll", final_poll.status, [200, 201])

    final_commands: List[Dict[str, Any]] = []
    if isinstance(final_poll.body, list):
        final_commands = [c for c in final_poll.body if isinstance(c, dict)]
    elif isinstance(final_poll.body, dict):
        c = final_poll.body.get("commands")
        if isinstance(c, list):
            final_commands = [x for x in c if isinstance(x, dict)]

    lingering = [c for c in final_commands if int(c.get("id", -1)) == command_id]
    if lingering:
        raise FlowError(f"command id {command_id} still appears pending after result post")

    print("[OK] Reprovision + command relay flow validation passed.")


def parse_args(argv: List[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Validate reprovision + command relay flows against Unit Connector")
    p.add_argument("--uc-url", required=True, help="Unit Connector base URL, e.g. https://example.com")
    p.add_argument("--unit-id", required=True, help="Target unit_id")
    p.add_argument("--admin-key", required=True, help="X-TMON-ADMIN key for admin/device/settings")
    p.add_argument("--command-type", default="set_var", help="Command type to enqueue (default: set_var)")
    p.add_argument("--command-key", default="DEBUG", help="Command payload key for set_var")
    p.add_argument("--command-value", default="1", help="Command payload value for set_var")
    p.add_argument("--poll-retries", type=int, default=6, help="Queue poll attempts before failure")
    p.add_argument("--poll-delay-s", type=float, default=1.0, help="Delay between queue polls")
    return p.parse_args(argv)


def main(argv: List[str]) -> int:
    args = parse_args(argv)
    try:
        run_validation(
            uc_url=args.uc_url,
            unit_id=args.unit_id,
            admin_key=args.admin_key,
            command_type=args.command_type,
            command_key=args.command_key,
            command_value=args.command_value,
            poll_retries=args.poll_retries,
            poll_delay_s=args.poll_delay_s,
        )
        return 0
    except FlowError as e:
        print(f"[FAIL] {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"[FAIL] unexpected error: {e}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
