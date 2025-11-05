from __future__ import annotations

from amongus_reader.service.data_service import AmongUsDataService


class SessionReader:
    def __init__(self, ds: AmongUsDataService) -> None:
        self._ds = ds

    def state(self) -> str:
        try:
            if not self._ds.is_attached():
                self._ds.attach()
            lp = self._ds._get_local_player_ptr()
            npi = self._ds._get_all_npi_objects()
            if not lp and not npi:
                return "LOBBY"
            try:
                local_id = self._ds.get_local_player_id()
                if local_id is None:
                    return "MATCHING"
                tasks = self._ds.get_tasks_for_player(local_id)
                if tasks and len(tasks) > 0:
                    return "SHIP"
            except Exception:
                pass
            return "MATCHING"
        except Exception:
            return "Unknown"
