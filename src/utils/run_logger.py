"""Per-stage run logging: console + JSON file under logs/.

The JSON files double as a transparency record (scenes found/rejected/accepted)
for reporting.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path


class RunLogger:
    def __init__(self, stage: str, log_dir: str = "logs", level: str = "INFO"):
        self.stage = stage
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.started = datetime.now(timezone.utc)
        self.events: list[dict] = []
        self.summary: dict = {}
        self.log = logging.getLogger(stage)
        if not logging.getLogger().handlers:
            logging.basicConfig(
                level=getattr(logging, level.upper(), logging.INFO),
                format="%(asctime)s %(name)s %(levelname)s %(message)s",
            )

    def event(self, message: str, **fields) -> None:
        self.log.info("%s%s", message, f" {fields}" if fields else "")
        self.events.append(
            {"t": datetime.now(timezone.utc).isoformat(), "message": message, **fields}
        )

    def warning(self, message: str, **fields) -> None:
        self.log.warning("%s%s", message, f" {fields}" if fields else "")
        self.events.append(
            {"t": datetime.now(timezone.utc).isoformat(), "level": "warning",
             "message": message, **fields}
        )

    def set_summary(self, **fields) -> None:
        self.summary.update(fields)

    def finish(self) -> Path:
        payload = {
            "stage": self.stage,
            "started": self.started.isoformat(),
            "finished": datetime.now(timezone.utc).isoformat(),
            "summary": self.summary,
            "events": self.events,
        }
        out = self.log_dir / f"run_{self.stage}_{self.started.strftime('%Y%m%dT%H%M%S')}.json"
        out.write_text(json.dumps(payload, indent=2, default=str))
        self.log.info("run log written: %s", out)
        return out
