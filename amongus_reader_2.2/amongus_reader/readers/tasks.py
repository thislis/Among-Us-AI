from __future__ import annotations

from typing import List

from amongus_reader.service.data_service import AmongUsDataService, TaskData


class TasksReader:
    def __init__(self, ds: AmongUsDataService) -> None:
        self._ds = ds

    def get_tasks(self, player_id: int) -> List[TaskData]:
        return self._ds.get_tasks_for_player(player_id)
