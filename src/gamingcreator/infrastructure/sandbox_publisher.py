"""Publishing adapter boundary with a local sandbox target only.

The sandbox walks a verified package through submitted → processing → published on this machine
so the publishing flow (eligibility, persisted status, status retrieval, retry after failure)
can be exercised. It never uploads anything and never contacts a platform. Real platform
targets require official access, account permission and the user's explicit approval first.
"""

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from gamingcreator.infrastructure.local_paths import is_link

STATES = ("submitted", "processing", "published")
REAL_TARGETS = {"bilibili", "douyin", "kuaishou", "xiaohongshu"}


class SandboxPublisher:
    def __init__(self, repository: Path) -> None:
        self.root = repository.resolve() / ".cache/workspace/publishing"

    def _directory(self) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        if any(is_link(p) for p in (self.root, *self.root.parents)):
            raise ValueError("发布记录目录不能使用链接。")
        return self.root

    def _path(self, publish_id: str) -> Path:
        if re.fullmatch(r"[0-9a-f]{32}", publish_id) is None:
            raise ValueError("无效发布记录编号。")
        return self._directory() / f"{publish_id}.json"

    def submit(self, package_job_id: str, package: dict[str, Any], target: str) -> dict[str, Any]:
        if target in REAL_TARGETS:
            raise PermissionError(
                "真实平台发布尚未接入：需要官方开放接口、账号授权和你的明确同意。现在只能用沙箱模拟。"
            )
        if target != "sandbox":
            raise ValueError("发布目标只能是 sandbox（本机模拟）。")
        if package.get("localChecks") != "pass":
            raise ValueError("发布包的本地检查未通过，不能发布。")
        if package.get("publicationEligibility") == "blocked":
            raise ValueError("发布包被标记为不可发布（例如素材仅供测试），不能发布。")
        now = datetime.now(UTC).isoformat()
        publish_id = uuid4().hex
        record = {
            "schemaVersion": "sandbox-publish-v1",
            "publishId": publish_id,
            "packageJobId": package_job_id,
            "platform": package.get("profile", {}).get("Platform"),
            "target": "sandbox",
            "remoteId": "sandbox-"
            + hashlib.sha256(f"{package_job_id}:{publish_id}".encode()).hexdigest()[:12],
            "state": "submitted",
            "events": [{"state": "submitted", "at": now}],
            "simulation": True,
            "note": "本机模拟：未上传任何文件，未连接任何平台。",
        }
        with self._path(publish_id).open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
        return record

    def status(self, publish_id: str) -> dict[str, Any]:
        """Each status check advances the simulation by one step until published."""
        path = self._path(publish_id)
        record: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        if record.get("publishId") != publish_id or record.get("simulation") is not True:
            raise ValueError("发布记录与编号不符。")
        if record["state"] != "published":
            record["state"] = STATES[STATES.index(record["state"]) + 1]
            record["events"].append({"state": record["state"], "at": datetime.now(UTC).isoformat()})
            temporary = path.with_suffix(".partial")
            temporary.write_text(
                json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            temporary.replace(path)
        return record

    def history(self, package_job_id: str) -> list[dict[str, Any]]:
        records = []
        for path in sorted(self._directory().glob("*.json")):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if record.get("packageJobId") == package_job_id:
                records.append(record)
        return sorted(records, key=lambda r: r["events"][0]["at"])
