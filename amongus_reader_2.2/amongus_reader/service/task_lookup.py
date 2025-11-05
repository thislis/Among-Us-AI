from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple, TYPE_CHECKING

from collections import Counter

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .data_service import TaskData


TASK_TYPE_NAMES: Dict[int, str] = {
    0x00: "Submit Scan",
    0x01: "Prime Shields",
    0x02: "Fuel Engines",
    0x03: "Chart Course",
    0x04: "Start Reactor",
    0x05: "Swipe Card",
    0x06: "Clear Asteroids",
    0x07: "Download Data",
    0x09: "Empty Chute",
    0x0B: "Align Engine Output",
    0x0C: "Fix Wiring",
    0x0E: "Divert Power",
    0x12: "Clean O2 Filter",
    0x14: "Restore Oxygen",
    0x15: "Stabilize Steering",
    0x1C: "Run Diagnostics",
}


TASK_COORDS_SHIP: Dict[str, Dict[str, Tuple[float, float]]] = {
    "Submit Scan": {"MedBay": (-7.19, -5.17)},
    "Prime Shields": {"Shields": (7.52, -14.48)},
    "Fuel Engines": {
        "Storage": (-3.28, -14.32),
        "Upper Engine": (-18.04, -0.61),
        "Lower Engine": (-18.01, -12.81),
    },
    "Chart Course": {"Navigation": (17.43, -3.12)},
    "Start Reactor": {"Reactor": (-21.47, -6.12)},
    "Swipe Card": {"Admin": (5.92, -9.02)},
    "Clear Asteroids": {"Weapons": (8.71, 1.26)},
    "Download Data": {
        "Communications": (4.30, -14.87),
        "Admin": (2.69, -6.87),
        "Electrical": (-9.88, -8.05),
        "Navigation": (16.92, -3.12),
        "Weapons": (8.71, 3.37),
    },
    "Align Engine Output": {
        "Upper Engine": (-19.36, -1.22),
        "Lower Engine": (-18.92, -13.43),
    },
    "Fix Wiring": {
        "Navigation": (14.59, -4.70),
        "Cafeteria": (-5.06, 4.79),
        "Security": (-15.54, -5.16),
        "Electrical": (-7.59, -8.11),
        "Storage": (-1.97, -9.40),
        "Admin": (1.28, -6.98),
    },
    "Empty Chute": {
        "Oxygen": (5.13, -3.80),
        "Storage": (0.59, -16.96),
    },
    "Divert Power": {
        "Electrical": (-8.96, -8.07),
        "Security": (-12.25, -3.52),
        "Communications": (6.33, -14.73),
        "Weapons": (11.18, 1.64),
        "Navigation": (16.03, -3.11),
        "Upper Engine": (-17.15, 2.62),
        "Lower Engine": (-18.07, -9.88),
        "Oxygen": (8.31, -3.15),
        "Shields": (10.80, -10.72),
    },
    "Clean O2 Filter": {"Oxygen": (6.06, -3.31)},
    "Restore Oxygen": {"Oxygen": (6.75, -3.43)},
    "Stabilize Steering": {"Navigation": (0.0, 0.0)},
}


MULTISTEP_HINT: Dict[int, int] = {
    0x02: 2,  # Fuel Engines
    0x07: 2,  # Download/Upload Data
    0x0B: 2,  # Align Engine Output
    0x0C: 3,  # Fix Wiring
    0x0E: 2,  # Divert Power
}


ROOM_ALIASES: Dict[str, str] = {
    "O2": "Oxygen",
}


DIVERT_DEST_PRIORITY = [
    "Weapons",
    "Navigation",
    "Shields",
    "Communications",
    "Upper Engine",
    "Lower Engine",
    "Oxygen",
    "Security",
]


SYSTEM_TYPE_NAMES: Dict[int, str] = {
    0x00: "Hallway",
    0x01: "Storage",
    0x02: "Cafeteria",
    0x03: "Reactor",
    0x04: "Upper Engine",
    0x05: "Navigation",
    0x06: "Admin",
    0x07: "Electrical",
    0x08: "Oxygen",
    0x09: "Shields",
    0x0A: "MedBay",
    0x0B: "Security",
    0x0C: "Weapons",
    0x0D: "Lower Engine",
    0x0E: "Communications",
    0x0F: "Ship Tasks",
    0x10: "Doors",
    0x11: "Sabotage",
    0x12: "Decontamination",
    0x13: "Launchpad",
    0x14: "Locker Room",
    0x15: "Laboratory",
    0x16: "Balcony",
    0x17: "Office",
    0x18: "Greenhouse",
    0x19: "Dropship",
    0x1A: "Decontamination",
    0x1B: "Outside",
    0x1C: "Specimens",
    0x1D: "Boiler Room",
    0x1E: "Vault",
    0x1F: "Cockpit",
    0x20: "Armory",
    0x21: "Kitchen",
    0x22: "Viewing Deck",
    0x23: "Hall of Portraits",
    0x24: "Cargo Bay",
    0x25: "Ventilation",
    0x26: "Showers",
    0x27: "Engine Room",
    0x28: "Brig",
    0x29: "Meeting Room",
    0x2A: "Records",
    0x2B: "Lounge",
    0x2C: "Gap Room",
    0x2D: "Main Hall",
    0x2E: "Medical",
    0x2F: "Decontamination",
    0x30: "Zipline",
    0x31: "Mining Pit",
    0x32: "Fishing Dock",
    0x33: "Rec Room",
    0x34: "Lookout",
    0x35: "Beach",
    0x36: "Highlands",
    0x37: "Jungle",
    0x38: "Sleeping Quarters",
}


def task_type_name(task_type_id: int) -> str:
    return TASK_TYPE_NAMES.get(int(task_type_id), f"TaskType#{task_type_id}")


def normalize_room_label(room: Optional[str]) -> Optional[str]:
    if room is None:
        return None
    canonical = ROOM_ALIASES.get(room)
    if canonical:
        return canonical
    return room


def display_room(room: Optional[str]) -> str:
    if not room:
        return "Unknown"
    for alias, canonical in ROOM_ALIASES.items():
        if canonical.lower() == room.lower():
            return alias
    return room


def resolve_task_location(
    task_type_id: int,
    preferred_room: Optional[str] = None,
) -> Tuple[str, str, Optional[Tuple[float, float]]]:
    name = task_type_name(task_type_id)
    room_map = TASK_COORDS_SHIP.get(name, {})
    if not room_map:
        return name, "Unknown", None
    canonical_pref = normalize_room_label(preferred_room)
    if canonical_pref and canonical_pref in room_map:
        return name, canonical_pref, room_map[canonical_pref]
    first_room, coord = next(iter(room_map.items()))
    return name, first_room, coord


def system_type_to_name(system_id: Optional[int]) -> Optional[str]:
    if system_id is None:
        return None
    return SYSTEM_TYPE_NAMES.get(int(system_id))


def choose_divert_destination(current_room: Optional[str]) -> Optional[str]:
    canonical_current = normalize_room_label(current_room)
    for candidate in DIVERT_DEST_PRIORITY:
        candidate_canonical = normalize_room_label(candidate)
        if candidate_canonical and candidate_canonical != canonical_current:
            return candidate
    return None


@dataclass
class TaskPanelEntry:
    room: str
    task_name: str
    completed_steps: Optional[int]
    total_steps: Optional[int]
    task_id: int
    task_type_id: int
    coordinates: Optional[Tuple[float, float]]
    canonical_room: Optional[str] = None

    def progress_suffix(self) -> str:
        if self.total_steps and self.total_steps > 1:
            return f"({self.completed_steps or 0}/{self.total_steps})"
        return ""

    def display_text(self) -> str:
        suffix = self.progress_suffix()
        if suffix:
            return f"{self.room}: {self.task_name} {suffix}"
        return f"{self.room}: {self.task_name}"


def format_task_entry(
    task: "TaskData",
    totals: Counter,
    completed_counts: Counter,
) -> TaskPanelEntry:
    base_name = task_type_name(task.task_type_id)
    resolved_name, canonical_room, coord = resolve_task_location(task.task_type_id, task.location)
    room_canonical = canonical_room
    preferred = normalize_room_label(task.location)
    if preferred:
        room_canonical = preferred
        if coord is None:
            # try lookup with canonical preferred room
            _, _, coord_pref = resolve_task_location(task.task_type_id, preferred)
            coord = coord_pref
    elif task.location:
        # If custom label provided but no mapping, keep as-is for display
        room_canonical = task.location

    if coord is None:
        # best-effort fallback
        _, _, coord = resolve_task_location(task.task_type_id)

    if task.step is not None and task.max_step is not None:
        completed_steps = int(task.step)
        total_steps = max(int(task.max_step), 1)
    else:
        total_steps = totals.get(task.task_type_id, 1)
        if total_steps <= 1 and task.task_type_id in MULTISTEP_HINT:
            total_steps = MULTISTEP_HINT[task.task_type_id]
        completed_steps = completed_counts.get(task.task_type_id, 0)

    room_display = display_room(room_canonical)
    name_display = base_name if base_name != resolved_name else resolved_name

    if task.task_type_id == 0x0E:  # Divert Power stages
        dest = task.destination
        if not dest and room_canonical and room_canonical.lower() == "electrical":
            dest = choose_divert_destination(room_canonical)
        if dest:
            name_display = f"Divert Power to {dest}"
        elif room_canonical and room_canonical.lower() != "electrical":
            name_display = "Accept Diverted Power"

    entry = TaskPanelEntry(
        room=room_display,
        task_name=name_display,
        completed_steps=completed_steps,
        total_steps=total_steps,
        task_id=int(task.task_id),
        task_type_id=int(task.task_type_id),
        coordinates=coord,
        canonical_room=room_canonical,
    )
    return entry

