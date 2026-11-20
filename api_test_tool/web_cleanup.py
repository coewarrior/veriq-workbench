"""Server-side adapter with only SELECT/DELETE on the isolated demonstration table."""
from __future__ import annotations

import os
import re


def gomoku_mysql_cleanup(bundle: dict):
    owned = {case["id"] for case in bundle.get("cases", [])
             if case.get("variables", {}).get("username") == {"kind": "unique", "prefix": "mvp_"}}
    password = os.environ.get("GOMOKU_CLEANUP_PASSWORD", "")
    if not password:
        raise ValueError("服务器尚未配置五子棋测试数据清理账户")

    def cleanup(contexts):
        import pymysql

        names = set()
        for context in contexts:
            if context["case_id"] in owned:
                value = context["variables"].get("username")
                if not isinstance(value, str) or not re.fullmatch(r"mvp_[A-Za-z0-9_-]{1,252}", value):
                    return {"status": "FAIL", "details": "测试数据超出本轮命名空间，清理未执行"}
                names.add(value)
        if not names:
            return {"status": "PASS", "details": {"deleted": 0, "remaining": 0}}
        try:
            with pymysql.connect(host=os.environ.get("GOMOKU_CLEANUP_HOST", "ai-api-gomoku-db-1"),
                                 user="gomoku_web_cleanup", password=password, database="gomoku_api_test",
                                 connect_timeout=5, read_timeout=10, write_timeout=10, charset="utf8mb4") as connection:
                with connection.cursor() as cursor:
                    placeholders = ",".join(["%s"] * len(names))
                    values = tuple(sorted(names))
                    cursor.execute(f"DELETE FROM `user` WHERE BINARY username IN ({placeholders})", values)
                    deleted = cursor.rowcount
                    cursor.execute(f"SELECT COUNT(*) FROM `user` WHERE BINARY username IN ({placeholders})", values)
                    remaining = cursor.fetchone()[0]
                connection.commit()
            return {"status": "PASS" if remaining == 0 else "FAIL", "details": {
                "adapter": "gomoku_mysql", "owned_usernames": len(names), "deleted": deleted, "remaining": remaining,
                "scope": "仅删除本轮独立测试账号；未清空数据库，未重启服务"}}
        except pymysql.MySQLError:
            return {"status": "FAIL", "details": "独立测试数据库清理失败，请检查服务器清理账户或连接"}

    return cleanup
