from __future__ import annotations

from typing import Any, Dict, Optional, Tuple
import time

from amongus_reader.service.data_service import AmongUsDataService


class HudReader:
    def __init__(self, ds: AmongUsDataService, min_interval: float = 1.5, time_budget: float = 0.10) -> None:
        self._ds = ds
        self._min_interval = float(min_interval)
        self._time_budget = float(time_budget)
        self._last_scan_ts: float = 0.0
        self._last_result: Optional[Tuple[Optional[bool], Dict[str, Any]]] = None

    def is_report_active(self) -> Tuple[Optional[bool], Dict[str, Any]]:
        now = time.time()
        if self._last_result is not None and (now - self._last_scan_ts) < self._min_interval:
            return self._last_result
        try:
            # best-effort to apply time budget before calling DS
            try:
                self._ds.set_report_scan_budget(self._time_budget)
            except Exception:
                pass
            res = self._ds.is_report_button_active()
        except Exception:
            res = (None, {"error": "hud_scan_failed"})
        self._last_result = res
        self._last_scan_ts = now
        return res

    def configure(self, min_interval: Optional[float] = None, time_budget: Optional[float] = None) -> None:
        if min_interval is not None:
            try:
                self._min_interval = max(0.05, float(min_interval))
            except Exception:
                pass
        if time_budget is not None:
            try:
                self._time_budget = max(0.05, float(time_budget))
            except Exception:
                pass
