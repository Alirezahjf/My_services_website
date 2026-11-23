"""Minimal, read-only GitHub REST client. Secrets are never logged or persisted."""
import requests
from flask import current_app


class GitHubError(RuntimeError):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


class GitHubClient:
    def __init__(self):
        self.base_url = current_app.config["GITHUB_API_URL"].rstrip("/")
        self.timeout = current_app.config["GITHUB_TIMEOUT"]
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/vnd.github+json", "User-Agent": "ServicesCatalog/1.0", "X-GitHub-Api-Version": "2022-11-28"})
        token = current_app.config.get("GITHUB_TOKEN")
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"

    def _get(self, path, **kwargs):
        try:
            response = self.session.get(f"{self.base_url}{path}", timeout=self.timeout, **kwargs)
        except requests.RequestException as exc:
            raise GitHubError("ارتباط با GitHub برقرار نشد. اتصال شبکه را بررسی کنید.") from exc
        if response.status_code == 403 and response.headers.get("X-RateLimit-Remaining") == "0":
            raise GitHubError("سهمیه GitHub API تمام شده است. بعداً تلاش کنید یا توکن فقط‌خواندنی تنظیم کنید.", 403)
        if response.status_code == 404:
            raise GitHubError("مخزن یا مسیر درخواستی پیدا نشد یا دسترسی مجاز نیست.", 404)
        if response.status_code == 401:
            raise GitHubError("احراز هویت GitHub نامعتبر است.", 401)
        if not response.ok:
            raise GitHubError(f"GitHub با خطای HTTP {response.status_code} پاسخ داد.", response.status_code)
        return response

    def repository_snapshot(self, owner, name, branch="main"):
        safe_owner, safe_name = owner.strip(), name.strip()
        if not safe_owner.replace("-", "").replace("_", "").isalnum() or not safe_name.replace("-", "").replace("_", "").replace(".", "").isalnum():
            raise GitHubError("نام مالک یا مخزن معتبر نیست.")
        repo = self._get(f"/repos/{safe_owner}/{safe_name}").json()
        selected_branch = branch or repo.get("default_branch", "main")
        commits = self._get(f"/repos/{safe_owner}/{safe_name}/commits", params={"sha": selected_branch, "per_page": 1}).json()
        try:
            readme_data = self._get(f"/repos/{safe_owner}/{safe_name}/readme").json()
        except GitHubError as exc:
            if exc.status != 404:
                raise
            readme_data = None
        releases_response = self._get(f"/repos/{safe_owner}/{safe_name}/releases", params={"per_page": 1})
        releases = releases_response.json()
        commit = commits[0] if commits else {}
        return {
            "metadata": {
                "description": repo.get("description") or "", "default_branch": repo.get("default_branch"),
                "language": repo.get("language"), "archived": repo.get("archived"),
                "visibility": repo.get("visibility"), "updated_at": repo.get("updated_at"),
                "html_url": repo.get("html_url"),
            },
            "commit": {"sha": commit.get("sha"), "message": (commit.get("commit") or {}).get("message", ""), "date": ((commit.get("commit") or {}).get("committer") or {}).get("date")},
            "readme_sha": (readme_data or {}).get("sha"),
            "release": releases[0].get("tag_name") if releases else None,
        }
