"""Trusted, narrowly scoped cleanup adapters. YAML never supplies executable code."""
from __future__ import annotations

import re
import shlex
import subprocess
from pathlib import Path


def build_cleanup(bundle: dict, environment: dict):
    config = environment.get("cleanup", {})
    mode = config.get("mode", "none")
    if mode == "none":
        return None
    if mode != "gomoku_ssh":
        raise ValueError(f"Unsupported cleanup adapter: {mode}")
    # This adapter is deliberately limited to the explicitly provisioned test DB.
    expected = {
        "host": "192.0.2.20", "user": "veriq",
        "project_dir": "/home/veriq/apps/ai-api-gomoku",
        "database": "gomoku_api_test", "table": "user",
        "identity_variable": "username",
    }
    if any(config.get(key) != value for key, value in expected.items()):
        raise ValueError("gomoku_ssh cleanup must target the dedicated gomoku_api_test deployment")
    if environment.get("base_url", "").rstrip("/") != "http://192.0.2.20:18081":
        raise ValueError("Cleanup target does not match the test API environment")
    identity = Path(config.get("identity_file", "")).expanduser()
    if not identity.is_file():
        raise ValueError("SSH identity file is unavailable for test-data cleanup")
    owned_cases = {
        case["id"] for case in bundle.get("cases", [])
        if case.get("variables", {}).get("username", {}).get("kind") == "unique"
        and case["variables"]["username"].get("prefix") == "mvp_"
    }

    def cleanup(contexts: list[dict]) -> dict:
        usernames = set()
        for context in contexts:
            if context.get("case_id") not in owned_cases:
                continue
            username = context.get("variables", {}).get("username")
            if username is None:
                continue
            if not isinstance(username, str) or not re.fullmatch(r"mvp_[A-Za-z0-9_-]{1,252}", username):
                return {"status": "FAIL", "details": "Generated username is outside the owned cleanup namespace"}
            usernames.add(username)
        if not usernames:
            return {"status": "PASS", "details": {"owned_usernames": 0, "deleted": 0, "remaining": 0}}
        # Safe because every value is restricted to the ASCII identifier alphabet above.
        values = ",".join("'" + name + "'" for name in sorted(usernames))
        where = "BINARY username IN (" + values + ")"
        sql = ("USE gomoku_api_test;\nSTART TRANSACTION;\n"
               f"DELETE FROM `user` WHERE {where};\nSELECT ROW_COUNT();\n"
               f"SELECT COUNT(*) FROM `user` WHERE {where};\nCOMMIT;\n")
        db_shell = 'export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"; exec mysql -uroot --batch --skip-column-names'
        remote = ("cd " + shlex.quote(expected["project_dir"])
                  + " && docker compose exec -T db sh -c " + shlex.quote(db_shell))
        command = ["ssh", "-i", str(identity), "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
                   "-o", "ConnectTimeout=8", "-o", "StrictHostKeyChecking=yes",
                   expected["user"] + "@" + expected["host"], remote]
        try:
            process = subprocess.run(command, input=sql, text=True, capture_output=True, timeout=30)
            counts = [int(line) for line in process.stdout.splitlines() if line.strip().isdigit()]
            if process.returncode != 0 or len(counts) != 2:
                return {"status": "FAIL", "details": "SSH/MySQL cleanup failed; inspect the dedicated deployment locally"}
            return {"status": "PASS" if counts[1] == 0 else "FAIL", "details": {
                "adapter": "gomoku_ssh", "owned_usernames": len(usernames),
                "deleted": counts[0], "remaining": counts[1],
                "scope": "Only this run's unique mvp_ usernames; API process was not restarted",
            }}
        except (OSError, subprocess.TimeoutExpired):
            return {"status": "FAIL", "details": "SSH cleanup unavailable or timed out"}

    return cleanup
