"""Schlanker GitHub-Issues-Client (REST v3) für die Alarm-Issues.

Nur die wenigen Operationen, die ``alert_issues.py`` braucht: offene Issues mit
einem Label auflisten, Issue anlegen, kommentieren, Body/Status ändern, Label
sicherstellen. Authentifizierung über ein Token (GitHub-Actions-``GITHUB_TOKEN``).
Netz-Code; die Alarm-Logik selbst steht netzfrei in :mod:`alerts`.
"""

from __future__ import annotations

import requests

from .config import HTTP_TIMEOUT, USER_AGENT

API_BASE = "https://api.github.com"


class GitHubIssues:
    """Dünne Hülle um die GitHub-REST-API für ein einzelnes Repo (``owner/name``)."""

    def __init__(self, repo: str, token: str, base: str = API_BASE) -> None:
        if not repo or "/" not in repo:
            raise ValueError(f"repo muss 'owner/name' sein, nicht {repo!r}")
        self.repo = repo
        self.base = base.rstrip("/")
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": USER_AGENT,
            }
        )

    def _url(self, path: str) -> str:
        return f"{self.base}/repos/{self.repo}/{path.lstrip('/')}"

    def list_open_issues(self, label: str) -> list[dict]:
        """Offene Issues (keine PRs) mit ``label`` inkl. Body und Nummer."""
        out: list[dict] = []
        page = 1
        while True:
            r = self._session.get(
                self._url("issues"),
                params={
                    "state": "open",
                    "labels": label,
                    "per_page": 100,
                    "page": page,
                },
                timeout=HTTP_TIMEOUT,
            )
            r.raise_for_status()
            batch = r.json()
            if not batch:
                break
            out.extend(i for i in batch if "pull_request" not in i)
            if len(batch) < 100:
                break
            page += 1
        return out

    def ensure_label(
        self, name: str, color: str = "b60205", description: str = ""
    ) -> None:
        """Label anlegen; existiert es schon (422), still ignorieren."""
        r = self._session.post(
            self._url("labels"),
            json={"name": name, "color": color, "description": description},
            timeout=HTTP_TIMEOUT,
        )
        if r.status_code not in (201, 422):
            r.raise_for_status()

    def create_issue(self, title: str, body: str, labels: list[str]) -> dict:
        r = self._session.post(
            self._url("issues"),
            json={"title": title, "body": body, "labels": labels},
            timeout=HTTP_TIMEOUT,
        )
        r.raise_for_status()
        return r.json()

    def comment(self, number: int, body: str) -> dict:
        r = self._session.post(
            self._url(f"issues/{number}/comments"),
            json={"body": body},
            timeout=HTTP_TIMEOUT,
        )
        r.raise_for_status()
        return r.json()

    def update_issue(
        self,
        number: int,
        *,
        body: str | None = None,
        state: str | None = None,
        state_reason: str | None = None,
    ) -> dict:
        payload: dict[str, str] = {}
        if body is not None:
            payload["body"] = body
        if state is not None:
            payload["state"] = state
        if state_reason is not None:
            payload["state_reason"] = state_reason
        r = self._session.patch(
            self._url(f"issues/{number}"), json=payload, timeout=HTTP_TIMEOUT
        )
        r.raise_for_status()
        return r.json()
