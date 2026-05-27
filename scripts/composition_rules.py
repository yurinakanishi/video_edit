from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Any


GOLDEN = (sqrt(5) - 1) / 2
GOLDEN_LEFT = 1 - GOLDEN
GOLDEN_RIGHT = GOLDEN
OUTER_GOLDEN_LEFT = GOLDEN_LEFT * GOLDEN
OUTER_GOLDEN_RIGHT = 1 - OUTER_GOLDEN_LEFT
THIRD_LEFT = 1 / 3
THIRD_RIGHT = 2 / 3
SILVER_LEFT = sqrt(2) - 1
SILVER_RIGHT = 1 - SILVER_LEFT
CENTER = 0.5

COMPOSITION_ANCHORS = {
    "center": CENTER,
    "third_left": THIRD_LEFT,
    "third_right": THIRD_RIGHT,
    "golden_left": GOLDEN_LEFT,
    "golden_right": GOLDEN_RIGHT,
    "outer_golden_left": OUTER_GOLDEN_LEFT,
    "outer_golden_right": OUTER_GOLDEN_RIGHT,
    "silver_left": SILVER_LEFT,
    "silver_right": SILVER_RIGHT,
}


@dataclass(frozen=True)
class CompositionTarget:
    x: float
    y: float
    anchor: str
    rule: str


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def nearest_anchor(value: float, anchors: dict[str, float] | None = None) -> tuple[str, float]:
    choices = anchors or COMPOSITION_ANCHORS
    return min(choices.items(), key=lambda item: abs(float(value) - item[1]))


def subject_target_for_face(face_direction: str, strength: str = "golden") -> CompositionTarget:
    if strength == "outer":
        left_anchor = ("outer_golden_left", OUTER_GOLDEN_LEFT)
        right_anchor = ("outer_golden_right", OUTER_GOLDEN_RIGHT)
    elif strength == "third":
        left_anchor = ("third_left", THIRD_LEFT)
        right_anchor = ("third_right", THIRD_RIGHT)
    elif strength == "silver":
        left_anchor = ("silver_left", SILVER_LEFT)
        right_anchor = ("silver_right", SILVER_RIGHT)
    else:
        left_anchor = ("golden_left", GOLDEN_LEFT)
        right_anchor = ("golden_right", GOLDEN_RIGHT)

    if face_direction == "left":
        name, x = right_anchor
        return CompositionTarget(
            x=x,
            y=GOLDEN_LEFT,
            anchor=name,
            rule="Face looks left; place the subject on the right golden anchor to leave look-space on the left.",
        )
    if face_direction == "right":
        name, x = left_anchor
        return CompositionTarget(
            x=x,
            y=GOLDEN_LEFT,
            anchor=name,
            rule="Face looks right; place the subject on the left golden anchor to leave look-space on the right.",
        )
    return CompositionTarget(
        x=CENTER,
        y=GOLDEN_LEFT,
        anchor="center",
        rule="Face direction is front or unknown; keep the subject centered and put the eyes near the upper golden line.",
    )


def crop_window_center_for_subject(subject_center: float, target_subject_x: float, visible_ratio: float) -> float:
    return clamp(subject_center - (target_subject_x - CENTER) * visible_ratio, 0.2, 0.8)


def visible_ratio_for_area(area_ratio: float) -> float:
    if area_ratio >= 0.32:
        return 0.74
    if area_ratio >= 0.20:
        return 0.84
    if area_ratio >= 0.12:
        return 0.92
    return 1.0


def bbox_center_ratio(box: Any, width: float, height: float) -> tuple[float, float]:
    x, y, w, h = [float(value) for value in box]
    return ((x + w / 2) / width, (y + h / 2) / height)


def rect_center_distance_score(
    box: Any,
    width: float,
    height: float,
    preferred_x: float,
    preferred_y: float = GOLDEN_LEFT,
) -> float:
    cx, cy = bbox_center_ratio(box, width, height)
    return abs(cx - preferred_x) + abs(cy - preferred_y) * 0.65
