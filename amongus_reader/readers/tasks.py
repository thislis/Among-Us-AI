from __future__ import annotations

from typing import List, Union

from amongus_reader.service.data_service import AmongUsDataService, TaskData, ColorId


class TasksReader:
    def __init__(self, ds: AmongUsDataService) -> None:
        self._ds = ds

    def get_tasks(self, color_id: Union[int, ColorId]) -> List[TaskData]:
        return self._ds.get_tasks_for_player_by_color(color_id)
