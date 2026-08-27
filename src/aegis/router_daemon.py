"""
Universal Aegis router daemon — OpenAI-compatible gateway.

POST /v1/chat/completions  → detect provider → optional Aegis pipeline → upstream
POST /v1/aegis/run          → full pipeline JSON
GET  /v1/aegis/status       → providers + budget signals
GET  /healthz

Does not claim savings without going through output_store.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

from aegis import DEFAULT_BATCH_WORKERS, __version__
from aegis.output_lane import activate_output, land_output, mode_default_profile
from aegis.providers import detect_provider
from aegis.router_client import chat_completion
from aegis.router_pipeline import run_pipeline, router_status

_DAEMON_STATE: Dict[str, Any] = {
    "host": "127.0.0.1",
    "port": 8787,
    "requests": 0,
    "pipeline_runs": 0,
}


class AegisRouterHandler(BaseHTTPRequestHandler):
    # Keep in sync with package version (not a hard-coded 1.0 / 0.13)
    server_version = f"AegisRouter/{__version__}"

    def log_message(self, fmt: str, *args: Any) -> None:
        return  # quiet

    def _read_json(self) -> Dict[str, Any]:
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b"{}"
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    def _write_json(self, code: int, body: Dict[str, Any]) -> None:
        data = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Aegis-Router", __version__)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        from urllib.parse import parse_qs

        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query or "")

        if path in ("/healthz", "/v1/health"):
            self._write_json(200, {"ok": True, "service": "aegis-router", "version": __version__})
            return
        if path in ("/v1/aegis/status", "/status"):
            st = router_status()
            st["daemon"] = dict(_DAEMON_STATE)
            self._write_json(200, st)
            return
        if path in ("/v1/aegis/evidence-yield", "/evidence-yield"):
            from aegis.evidence_yield import operational_projection

            body = operational_projection()
            body["version"] = __version__
            self._write_json(200, body)
            return
        if path in ("/v1/aegis/autoscan", "/autoscan"):
            from aegis.autoscan import status

            body = status()
            body["version"] = __version__
            self._write_json(200, body)
            return
        if path in ("/v1/aegis/budget", "/budget"):
            # Compact piggy-bank + surplus for menu bar / SwiftUI
            from aegis.fund import surplus_snapshot
            from aegis.ledger import generate_report

            report = generate_report()
            # drop full txn list from budget payload
            report.pop("transactions", None)
            body = {
                "ok": True,
                "budget": report,
                "surplus": surplus_snapshot(),
                "version": __version__,
            }
            self._write_json(200, body)
            return
        if path in ("/v1/aegis/ledger", "/ledger"):
            from aegis.ledger import filter_week, generate_report, read_all

            try:
                limit = int((qs.get("limit") or ["100"])[0])
            except (TypeError, ValueError):
                limit = 100
            limit = max(1, min(limit, 1000))
            week = (qs.get("week") or [None])[0]
            all_rows = read_all()
            if week:
                rows = filter_week(all_rows, week)
            else:
                rows = all_rows
            # newest first
            rows = list(reversed(rows))[:limit]
            summary = generate_report()
            summary.pop("transactions", None)
            self._write_json(
                200,
                {
                    "ok": True,
                    "count": len(rows),
                    "limit": limit,
                    "week": week or summary.get("week"),
                    "summary": summary,
                    "transactions": rows,
                    "version": __version__,
                },
            )
            return
        if path in ("/v1/aegis/spec", "/spec"):
            from aegis.api_contract import spec

            self._write_json(200, spec())
            return
        if path in ("/v1/aegis/kernel", "/kernel"):
            from aegis.kernel import syscall

            env = syscall("status")
            self._write_json(
                200,
                {
                    "ok": bool(env.get("ok")),
                    "kernel": env.get("result"),
                    "kid": env.get("kid"),
                    "elapsed_ms": env.get("elapsed_ms"),
                    "version": __version__,
                },
            )
            return
        if path in ("/v1/aegis/yield", "/yield"):
            from aegis.yield_proof import yield_report

            report = yield_report()
            self._write_json(
                200,
                {
                    "ok": True,
                    "yield": report,
                    "version": __version__,
                },
            )
            return
        if path in ("/v1/aegis/intel", "/intel", "/v1/aegis/intelligence"):
            from aegis.intelligence import intel_status

            body = intel_status()
            body["ok"] = True
            body["version"] = __version__
            self._write_json(200, body)
            return
        if path in ("/v1/aegis/forecast", "/forecast"):
            from aegis.forecast import predict_budget

            self._write_json(
                200, {"ok": True, "forecast": predict_budget(), "version": __version__}
            )
            return
        if path in ("/v1/aegis/burn", "/burn"):
            from aegis.burn import burn_status, recent_burn_events

            body = burn_status(record_events=True)
            body["recent_events"] = recent_burn_events(10)
            body["version"] = __version__
            self._write_json(200, body)
            return
        if path in ("/v1/aegis/budget-aware", "/budget-aware"):
            from aegis.budget_aware import evaluate, recent_budget_events

            dry = (qs.get("dry_run") or ["0"])[0] in ("1", "true", "yes")
            sim = (qs.get("simulate") or [None])[0]
            if sim:
                from aegis.budget_aware import simulate

                body = simulate(str(sim))
            else:
                body = evaluate(dry_run=dry)
            body["recent_events"] = recent_budget_events(10)
            body["version"] = __version__
            self._write_json(200, body)
            return
        if path in ("/v1/aegis/continuity", "/continuity"):
            from aegis.continuity import generate_bridge, latest_bridge_paths

            if (qs.get("latest") or ["0"])[0] in ("1", "true", "yes"):
                self._write_json(
                    200,
                    {"ok": True, "latest": latest_bridge_paths(), "version": __version__},
                )
                return
            bridge = generate_bridge(trigger="api")
            self._write_json(
                200,
                {
                    "ok": bridge.get("ok"),
                    "session_id": bridge.get("session_id"),
                    "paths": bridge.get("paths"),
                    "integrity_hash": (bridge.get("embedding_pack") or {}).get(
                        "integrity_hash"
                    ),
                    "version": __version__,
                },
            )
            return
        if path in ("/v1/models", "/models"):
            from aegis.providers import list_providers

            models = []
            for p in list_providers():
                models.append(
                    {
                        "id": f"{p['name']}/{p['default_model']}",
                        "object": "model",
                        "owned_by": p["name"],
                    }
                )
            self._write_json(200, {"object": "list", "data": models})
            return
        self._write_json(404, {"error": "not found"})

    def do_POST(self) -> None:
        _DAEMON_STATE["requests"] = int(_DAEMON_STATE.get("requests") or 0) + 1
        path = urlparse(self.path).path
        body = self._read_json()

        if path in ("/v1/aegis/intel/tick", "/intel/tick"):
            from aegis.intelligence import tick

            try:
                result = tick(force_report=bool(body.get("force_report")))
                self._write_json(200, result)
            except Exception as exc:  # noqa: BLE001
                self._write_json(500, {"ok": False, "error": str(exc)})
            return

        if path in ("/v1/aegis/evidence-yield/govern", "/evidence-yield/govern"):
            from aegis.evidence_yield import govern_claim

            try:
                result = govern_claim(
                    candidate_id=body.get("candidate_id") or "",
                    claim=body.get("claim") or "",
                    evidence=body.get("evidence") or [],
                    impact=body.get("impact") or "low",
                    active_outcome=body.get("active_outcome") or "",
                    provider=body.get("provider") or "",
                    model=body.get("model") or "",
                    request_id=body.get("request_id") or "",
                )
                self._write_json(200, {"ok": True, **result, "version": __version__})
            except (TypeError, ValueError) as exc:
                self._write_json(400, {"ok": False, "error": str(exc)})
            return

        if path in ("/v1/aegis/evidence-yield/outcome", "/evidence-yield/outcome"):
            from aegis.evidence_yield import record_verified_outcome

            try:
                result = record_verified_outcome(
                    candidate_id=body.get("candidate_id") or "",
                    domain=body.get("domain") or "",
                    verified=bool(body.get("verified")),
                    accepted=bool(body.get("accepted")),
                    review_minutes=float(body.get("review_minutes") or 0),
                    correction_minutes=float(body.get("correction_minutes") or 0),
                    cost_usd=body.get("cost_usd"),
                    cost_status=body.get("cost_status") or "unknown",
                    cost_source=body.get("cost_source") or "",
                    request_id=body.get("request_id") or "",
                )
                self._write_json(200, {"ok": True, "outcome": result, "version": __version__})
            except (TypeError, ValueError) as exc:
                self._write_json(400, {"ok": False, "error": str(exc)})
            return

        if path in ("/v1/aegis/autoscan/control", "/autoscan/control"):
            from aegis.autoscan import control

            try:
                payload = dict(body)
                action = payload.pop("action", "")
                result = control(action, **payload)
                self._write_json(200, {"ok": True, **result, "version": __version__})
            except (OSError, TypeError, ValueError) as exc:
                self._write_json(400, {"ok": False, "error": str(exc), "version": __version__})
            return

        if path in ("/v1/aegis/run", "/aegis/run"):
            _DAEMON_STATE["pipeline_runs"] = (
                int(_DAEMON_STATE.get("pipeline_runs") or 0) + 1
            )
            try:
                result = run_pipeline(
                    task=body.get("task") or body.get("prompt") or "router",
                    model=body.get("model") or "mock",
                    provider=body.get("provider") or "",
                    paths=body.get("paths") or [],
                    mode=body.get("mode") or "explore",
                    targets=body.get("targets") or [],
                    system=body.get("system") or "",
                    prompt=body.get("prompt") or body.get("task") or "",
                    profile=body.get("profile"),
                    skip_preflight=bool(body.get("skip_preflight")),
                    dry_run=bool(body.get("dry_run")),
                    max_tokens=int(body.get("max_tokens") or 1024),
                )
                self._write_json(200 if result.ok else 502, result.as_dict())
            except Exception as exc:  # noqa: BLE001
                self._write_json(500, {"ok": False, "error": str(exc)})
            return

        if path in ("/v1/chat/completions", "/chat/completions"):
            self._handle_chat(body)
            return

        self._write_json(404, {"error": "not found"})

    def _handle_chat(self, body: Dict[str, Any]) -> None:
        model = body.get("model") or "mock"
        # Aegis extensions via body or headers
        aegis = body.get("aegis") or {}
        use_pipeline = bool(
            aegis.get("pipeline")
            or self.headers.get("X-Aegis-Pipeline", "").lower() in ("1", "true")
        )
        paths = aegis.get("paths") or []
        task = aegis.get("task") or "chat"
        provider_name = aegis.get("provider") or ""

        if use_pipeline or paths:
            _DAEMON_STATE["pipeline_runs"] = (
                int(_DAEMON_STATE.get("pipeline_runs") or 0) + 1
            )
            # extract last user message as prompt
            prompt = task
            for m in reversed(body.get("messages") or []):
                if m.get("role") == "user":
                    prompt = m.get("content") or task
                    break
            result = run_pipeline(
                task=task,
                model=model,
                provider=provider_name,
                paths=paths,
                mode=aegis.get("mode") or "explore",
                prompt=prompt,
                system=aegis.get("system") or "",
                profile=aegis.get("profile"),
                dry_run=bool(aegis.get("dry_run")),
                max_tokens=int(body.get("max_tokens") or 1024),
            )
            # OpenAI-shaped response with Aegis extras
            content = result.shrunk or result.content
            self._write_json(
                200 if result.ok else 502,
                {
                    "id": f"aegis-{result.output_id or 'run'}",
                    "object": "chat.completion",
                    "model": result.model,
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": content},
                            "finish_reason": "stop" if result.ok else "error",
                        }
                    ],
                    "usage": result.usage,
                    "aegis": {
                        "provider": result.provider,
                        "pack_id": result.pack_id,
                        "output_id": result.output_id,
                        "output_reuse": result.output_reuse,
                        "mock": result.mock,
                        "error": result.error,
                    },
                },
            )
            return

        # Passthrough chat with post-hoc shrink/store (no pack)
        prov = detect_provider(model, provider_name)
        try:
            activate_output(profile=mode_default_profile("explore"), mode="explore")
            resp = chat_completion(
                prov,
                model=model,
                messages=body.get("messages") or [{"role": "user", "content": "hi"}],
                temperature=float(body.get("temperature") or 0.2),
                max_tokens=int(body.get("max_tokens") or 1024),
            )
            landed = land_output(
                body=resp.get("content") or "",
                summary=f"daemon-chat:{prov.name}",
                task=f"daemon:{prov.name}",
            )
            content = landed.get("shrunk_text") or resp.get("content") or ""
            self._write_json(
                200,
                {
                    "id": f"aegis-{landed.get('output_id') or 'chat'}",
                    "object": "chat.completion",
                    "model": resp.get("model"),
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": content},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": resp.get("usage") or {},
                    "aegis": {
                        "provider": resp.get("provider"),
                        "output_id": landed.get("output_id"),
                        "output_reuse": landed.get("output_reuse"),
                        "mock": resp.get("mock"),
                    },
                },
            )
        except Exception as exc:  # noqa: BLE001
            self._write_json(502, {"error": {"message": str(exc), "type": "aegis_router"}})


class _RouterServer(ThreadingHTTPServer):
    allow_reuse_address = True


def serve(host: str = "127.0.0.1", port: int = 8787) -> ThreadingHTTPServer:
    _DAEMON_STATE["host"] = host
    _DAEMON_STATE["port"] = port
    httpd = _RouterServer((host, port), AegisRouterHandler)
    return httpd


def serve_forever(host: str = "127.0.0.1", port: int = 8787) -> None:
    """Run router in-process; register PID/meta for daemon status + launchd."""
    import atexit
    import os
    import signal

    from aegis.daemon_control import clear_meta_if_pid, write_runtime_meta

    pid = os.getpid()
    write_runtime_meta(host, port, pid)
    _DAEMON_STATE["pid"] = pid
    _DAEMON_STATE["managed_by"] = os.environ.get("AEGIS_MANAGED_BY") or "foreground"

    # Intelligence Layer: autonomous compound ticks while router is up
    try:
        from aegis.intelligence import start_background_ticks

        _DAEMON_STATE["intel"] = start_background_ticks()
    except Exception as exc:  # noqa: BLE001
        _DAEMON_STATE["intel"] = {"ok": False, "error": str(exc)}

    try:
        from aegis.autoscan import start_background_autoscan

        _DAEMON_STATE["autoscan"] = start_background_autoscan()
    except Exception as exc:  # noqa: BLE001
        _DAEMON_STATE["autoscan"] = {"ok": False, "error": str(exc)}

    try:
        httpd = serve(host, port)
    except OSError as exc:
        err = str(exc)
        write_runtime_meta(
            host, port, pid, bind_ok=False, bind_error=err, bindError=err
        )
        print(f"[AEGIS ROUTER] bindError {host}:{port}: {exc}", flush=True)
        clear_meta_if_pid(pid)
        raise SystemExit(1) from exc
    write_runtime_meta(host, port, pid, bind_ok=True)
    cleaned = {"done": False}

    def _cleanup(*_args: Any) -> None:
        if cleaned["done"]:
            return
        cleaned["done"] = True
        clear_meta_if_pid(pid)
        try:
            httpd.shutdown()
        except Exception:  # noqa: BLE001
            pass

    def _on_term(_signum: int, _frame: Any) -> None:
        _cleanup()
        raise SystemExit(0)

    atexit.register(_cleanup)
    # launchd sends SIGTERM on bootout
    try:
        signal.signal(signal.SIGTERM, _on_term)
    except (ValueError, OSError):
        pass

    print(
        f"[AEGIS ROUTER v{__version__}] http://{host}:{port}/v1 "
        f"(chat + /v1/aegis/run + /v1/aegis/status) "
        f"concurrent≤{DEFAULT_BATCH_WORKERS} pid={pid}"
    )
    try:
        httpd.serve_forever()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        _cleanup()
        try:
            httpd.server_close()
        except Exception:  # noqa: BLE001
            pass


def start_background(host: str = "127.0.0.1", port: int = 8787) -> Tuple[ThreadingHTTPServer, threading.Thread]:
    httpd = serve(host, port)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd, t
