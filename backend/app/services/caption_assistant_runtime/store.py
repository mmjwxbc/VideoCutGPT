from __future__ import annotations

import json
import os
import tempfile
from threading import Lock
from typing import Dict

from app.core.config import settings
from app.models import CaptionSession, dump_session_record, load_session_record


class CaptionSessionStore:
    def __init__(self) -> None:
        self._sessions: Dict[str, CaptionSession] = {}
        self._lock = Lock()
        self._storage_dir = os.path.abspath(settings.session_store_dir)
        os.makedirs(self._storage_dir, exist_ok=True)
        self._load_existing_sessions()

    def save(self, session: CaptionSession) -> None:
        with self._lock:
            session.version += 1
            self._sessions[session.session_id] = session
            self._write_session_to_disk(session)

    def get(self, session_id: str) -> CaptionSession:
        with self._lock:
            if session_id not in self._sessions:
                raise KeyError(f"session '{session_id}' not found")
            return self._sessions[session_id]

    def list_by_user(self, owner_user_id: str, owner_email: str = "") -> list[CaptionSession]:
        with self._lock:
            sessions = [
                session
                for session in self._sessions.values()
                if self._session_matches_owner(
                    session,
                    owner_user_id=owner_user_id,
                    owner_email=owner_email,
                )
            ]
        return sorted(sessions, key=lambda session: session.updated_at, reverse=True)

    def _session_path(self, session_id: str) -> str:
        return os.path.join(self._storage_dir, f"{session_id}.json")

    def _load_existing_sessions(self) -> None:
        for file_name in sorted(os.listdir(self._storage_dir)):
            if not file_name.endswith(".json"):
                continue
            file_path = os.path.join(self._storage_dir, file_name)
            try:
                with open(file_path, "r", encoding="utf-8") as session_file:
                    payload = json.load(session_file)
                if not isinstance(payload, dict):
                    continue
                payload.setdefault("owner_user_id", settings.dev_access_user_id)
                payload.setdefault("owner_email", settings.dev_access_user_email)
                payload.setdefault("owner_name", settings.dev_access_user_name)
                session = load_session_record(payload)
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                continue
            self._sessions[session.session_id] = session

    def _write_session_to_disk(self, session: CaptionSession) -> None:
        payload = dump_session_record(session)
        session_path = self._session_path(session.session_id)
        fd, tmp_path = tempfile.mkstemp(
            prefix=f"{session.session_id}_",
            suffix=".tmp",
            dir=self._storage_dir,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as session_file:
                json.dump(payload, session_file, ensure_ascii=False, indent=2)
            os.replace(tmp_path, session_path)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def _session_matches_owner(
        self,
        session: CaptionSession,
        *,
        owner_user_id: str,
        owner_email: str,
    ) -> bool:
        if session.owner_user_id == owner_user_id:
            return True
        if owner_email and session.owner_email == owner_email:
            return True
        return False
