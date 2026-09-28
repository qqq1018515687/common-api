#!/usr/bin/env python3
"""供服务器定时器每三分钟调用；运行失败时返回非零退出码。"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from storage.database.channel_task_monitor import monitor_channel_tasks
from storage.database.db import get_session


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def main() -> int:
    db = get_session()
    try:
        result = monitor_channel_tasks(db)
        logging.info("[channel-monitor] 检查完成: %s", result)
        return 0
    except Exception:
        logging.exception("[channel-monitor] 检查失败")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
