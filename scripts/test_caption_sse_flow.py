from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path
from typing import Any

import httpx


DEFAULT_PROMPT = "请先生成适合投放的字幕初稿，并输出镜头级剪辑方案。"
DEFAULT_FOLLOWUP_PROMPT = "请把字幕语气改得更直接一些，并同步优化剪辑节奏。"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the caption assistant HTTP/SSE flow with a local video.",
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--video", default="backend/uploads/test.mp4")
    parser.add_argument("--platform", default="tiktok")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument(
        "--followup-prompt",
        action="append",
        dest="followup_prompts",
        default=[],
        help="Append a follow-up user prompt. Can be passed multiple times.",
    )
    parser.add_argument("--event-timeout", type=float, default=300.0)
    parser.add_argument("--overall-timeout", type=float, default=1800.0)
    return parser.parse_args()


async def get_next_line(lines: Any, timeout_seconds: float) -> str:
    try:
        return await asyncio.wait_for(lines.__anext__(), timeout=timeout_seconds)
    except StopAsyncIteration:
        raise EOFError("SSE stream ended") from None


async def fetch_session(client: httpx.AsyncClient, base_url: str, session_id: str) -> dict[str, Any]:
    response = await client.get(f"{base_url}/api/caption/assistant/session/{session_id}")
    response.raise_for_status()
    return response.json()


def summarize_session(label: str, session: dict[str, Any]) -> None:
    messages = session.get("messages") or []
    last_message = messages[-1] if messages else {}
    print(
        f"[{label}] "
        f"version={session.get('version')} "
        f"status={session.get('status')} "
        f"progress={session.get('progress_message')!r} "
        f"messages={len(messages)} "
        f"last_role={last_message.get('role', '-')} "
        f"last_preview={str(last_message.get('content', ''))[:80]!r}",
        flush=True,
    )


async def confirm_plan_once(
    client: httpx.AsyncClient,
    base_url: str,
    session: dict[str, Any],
    confirmed: bool,
) -> bool:
    if confirmed or session.get("status") != "awaiting_plan_selection":
        return confirmed

    plan_options = session.get("plan_options") or []
    selected_ids = session.get("selected_plan_ids") or [
        option["id"]
        for option in plan_options
        if option.get("required") or option.get("selected")
    ]
    required_ids = [
        option["id"]
        for option in plan_options
        if option.get("required")
    ]
    selected_ids = list(dict.fromkeys([*selected_ids, *required_ids]))

    print(f"[plan] confirming selected_plan_ids={selected_ids}", flush=True)
    response = await client.post(
        f"{base_url}/api/caption/assistant/session/{session['session_id']}/plan",
        json={"selected_plan_ids": selected_ids},
    )
    response.raise_for_status()
    confirmed_session = response.json()
    summarize_session("plan-confirmed", confirmed_session)
    return True


async def continue_turn(
    client: httpx.AsyncClient,
    base_url: str,
    session_id: str,
    prompt: str,
) -> dict[str, Any]:
    response = await client.post(
        f"{base_url}/api/caption/assistant/session/{session_id}/message",
        json={"prompt": prompt},
    )
    response.raise_for_status()
    session = response.json()
    summarize_session("followup-queued", session)
    return session


async def consume_turn_until_terminal(
    client: httpx.AsyncClient,
    base_url: str,
    session_id: str,
    event_timeout: float,
    overall_timeout: float,
    turn_label: str,
) -> dict[str, Any]:
    confirmed_plan = False
    event_count = 0
    started_at = time.monotonic()
    last_event_at = started_at
    event_name = "message"
    data_lines: list[str] = []
    terminal_statuses = {"completed", "error"}

    stream_url = f"{base_url}/api/caption/assistant/session/{session_id}/events"
    print(f"[{turn_label}] sse connect {stream_url}", flush=True)

    async with client.stream("GET", stream_url) as stream:
        stream.raise_for_status()
        lines = stream.aiter_lines()
        while True:
            if time.monotonic() - started_at > overall_timeout:
                raise TimeoutError(f"{turn_label} overall timeout {overall_timeout}s exceeded")

            line = await get_next_line(lines, event_timeout)
            if line.startswith(":"):
                continue

            if line == "":
                if not data_lines:
                    event_name = "message"
                    continue

                raw_data = "\n".join(data_lines)
                data_lines = []
                now = time.monotonic()
                gap = now - last_event_at
                last_event_at = now
                event_count += 1

                try:
                    payload = json.loads(raw_data)
                except json.JSONDecodeError:
                    payload = {"raw": raw_data}

                status = payload.get("status")
                progress = payload.get("progress_message") or payload.get("message")
                artifact = payload.get("artifact")
                version = payload.get("version")
                print(
                    f"[{turn_label}] "
                    f"#{event_count} +{gap:.1f}s "
                    f"event={event_name} "
                    f"version={version} "
                    f"status={status or '-'} "
                    f"artifact={artifact or '-'} "
                    f"progress={progress!r}",
                    flush=True,
                )

                if isinstance(payload, dict):
                    confirmed_plan = await confirm_plan_once(
                        client,
                        base_url,
                        payload,
                        confirmed_plan,
                    )
                    if payload.get("status") in terminal_statuses:
                        final_session = await fetch_session(client, base_url, session_id)
                        summarize_session(f"{turn_label}-final", final_session)
                        return final_session

                event_name = "message"
                continue

            if line.startswith("event:"):
                event_name = line.removeprefix("event:").strip()
            elif line.startswith("data:"):
                data_lines.append(line.removeprefix("data:").lstrip())


async def run_flow(args: argparse.Namespace) -> int:
    base_url = args.base_url.rstrip("/")
    video_path = Path(args.video)
    if not video_path.exists():
        print(f"[error] video not found: {video_path}", flush=True)
        return 2

    timeout = httpx.Timeout(
        connect=10.0,
        read=None,
        write=120.0,
        pool=10.0,
    )
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            health = await client.get(f"{base_url}/")
            health.raise_for_status()
        except Exception as exc:
            print(f"[error] backend is not reachable at {base_url}: {exc}", flush=True)
            return 2

        print(f"[create] uploading {video_path} to {base_url}", flush=True)
        with video_path.open("rb") as file_obj:
            response = await client.post(
                f"{base_url}/api/caption/assistant/session",
                data={
                    "platform": args.platform,
                    "prompt": args.prompt,
                },
                files={
                    "video": (video_path.name, file_obj, "video/mp4"),
                },
            )
        response.raise_for_status()
        session = response.json()
        session_id = session["session_id"]
        summarize_session("created", session)

        followup_prompts = args.followup_prompts or [DEFAULT_FOLLOWUP_PROMPT]

        try:
            latest_session = await consume_turn_until_terminal(
                client,
                base_url,
                session_id,
                args.event_timeout,
                args.overall_timeout,
                "turn-1",
            )
            if latest_session.get("status") != "completed":
                return 1

            for turn_index, prompt in enumerate(followup_prompts, start=2):
                print(f"[turn-{turn_index}] prompt={prompt!r}", flush=True)
                queued_session = await continue_turn(client, base_url, session_id, prompt)
                if queued_session.get("status") == "error":
                    return 1
                latest_session = await consume_turn_until_terminal(
                    client,
                    base_url,
                    session_id,
                    args.event_timeout,
                    args.overall_timeout,
                    f"turn-{turn_index}",
                )
                if latest_session.get("status") != "completed":
                    return 1

            return 0

        except (TimeoutError, asyncio.TimeoutError, EOFError) as exc:
            latest = await fetch_session(client, base_url, session_id)
            print(f"[timeout] {exc}", flush=True)
            summarize_session("latest", latest)
            return 1


def main() -> int:
    return asyncio.run(run_flow(parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
