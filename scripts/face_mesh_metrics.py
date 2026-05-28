from __future__ import annotations

import math
from typing import Any

import cv2


LEFT_EYE_CORNERS = (263, 362)
RIGHT_EYE_CORNERS = (33, 133)
LEFT_EYE_VERTICAL = (386, 374)
RIGHT_EYE_VERTICAL = (159, 145)
LEFT_IRIS = (473, 474, 475, 476, 477)
RIGHT_IRIS = (468, 469, 470, 471, 472)
MOUTH_CORNERS = (61, 291)
MOUTH_INNER = (13, 14)
MOUTH_OUTER = (0, 17)
HEAD_POSE_POINTS = (1, 234, 454)


def create_face_mesh(max_num_faces: int = 1, static_image_mode: bool = False) -> Any | None:
    try:
        import mediapipe as mp  # type: ignore
        return mp.solutions.face_mesh.FaceMesh(
            static_image_mode=static_image_mode,
            max_num_faces=max_num_faces,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
    except Exception:
        return None


def _point(landmarks: list[Any], index: int, width: int, height: int) -> tuple[float, float]:
    item = landmarks[index]
    return float(item.x) * width, float(item.y) * height


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _center(points: list[tuple[float, float]]) -> tuple[float, float]:
    return sum(point[0] for point in points) / len(points), sum(point[1] for point in points) / len(points)


def _landmark_bbox(landmarks: list[Any], width: int, height: int) -> dict[str, float]:
    xs = [max(0.0, min(float(width), float(item.x) * width)) for item in landmarks]
    ys = [max(0.0, min(float(height), float(item.y) * height)) for item in landmarks]
    return {
        "x1": round(min(xs), 2),
        "y1": round(min(ys), 2),
        "x2": round(max(xs), 2),
        "y2": round(max(ys), 2),
    }


def _mouth_open_label(open_ratio: float) -> str:
    if open_ratio >= 0.18:
        return "wide_open"
    if open_ratio >= 0.1:
        return "open"
    if open_ratio >= 0.045:
        return "slight"
    return "closed"


def mouth_metrics(landmarks: list[Any], width: int, height: int) -> dict[str, Any]:
    if len(landmarks) <= max(*MOUTH_CORNERS, *MOUTH_INNER, *MOUTH_OUTER):
        return {"available": False, "reason": "face mesh mouth landmarks unavailable"}
    left_corner = _point(landmarks, MOUTH_CORNERS[0], width, height)
    right_corner = _point(landmarks, MOUTH_CORNERS[1], width, height)
    upper_inner = _point(landmarks, MOUTH_INNER[0], width, height)
    lower_inner = _point(landmarks, MOUTH_INNER[1], width, height)
    upper_outer = _point(landmarks, MOUTH_OUTER[0], width, height)
    lower_outer = _point(landmarks, MOUTH_OUTER[1], width, height)
    mouth_width = max(1.0, _distance(left_corner, right_corner))
    inner_open = _distance(upper_inner, lower_inner)
    outer_open = _distance(upper_outer, lower_outer)
    open_ratio = inner_open / mouth_width
    return {
        "available": True,
        "method": "mediapipe_face_mesh_lip_landmarks",
        "open_ratio": round(open_ratio, 5),
        "inner_open_px": round(inner_open, 3),
        "outer_open_px": round(outer_open, 3),
        "mouth_width_px": round(mouth_width, 3),
        "label": _mouth_open_label(open_ratio),
    }


def _eye_gaze(
    landmarks: list[Any],
    *,
    iris_indices: tuple[int, ...],
    corner_indices: tuple[int, int],
    vertical_indices: tuple[int, int],
    width: int,
    height: int,
) -> dict[str, float] | None:
    if len(landmarks) <= max(*iris_indices, *corner_indices, *vertical_indices):
        return None
    corners = [_point(landmarks, index, width, height) for index in corner_indices]
    top = _point(landmarks, vertical_indices[0], width, height)
    bottom = _point(landmarks, vertical_indices[1], width, height)
    iris = _center([_point(landmarks, index, width, height) for index in iris_indices])
    min_x = min(point[0] for point in corners)
    max_x = max(point[0] for point in corners)
    min_y = min(top[1], bottom[1])
    max_y = max(top[1], bottom[1])
    eye_width = max(1.0, max_x - min_x)
    eye_height = max(1.0, max_y - min_y)
    return {
        "x_offset_ratio": ((iris[0] - min_x) / eye_width) - 0.5,
        "y_offset_ratio": ((iris[1] - min_y) / eye_height) - 0.5,
        "iris_x": iris[0],
        "iris_y": iris[1],
        "eye_width": eye_width,
        "eye_height": eye_height,
    }


def gaze_metrics(landmarks: list[Any], width: int, height: int) -> dict[str, Any]:
    eyes = [
        _eye_gaze(
            landmarks,
            iris_indices=LEFT_IRIS,
            corner_indices=LEFT_EYE_CORNERS,
            vertical_indices=LEFT_EYE_VERTICAL,
            width=width,
            height=height,
        ),
        _eye_gaze(
            landmarks,
            iris_indices=RIGHT_IRIS,
            corner_indices=RIGHT_EYE_CORNERS,
            vertical_indices=RIGHT_EYE_VERTICAL,
            width=width,
            height=height,
        ),
    ]
    usable = [eye for eye in eyes if eye is not None]
    if not usable:
        return {"available": False, "reason": "iris landmarks unavailable"}
    x_offset = sum(float(eye["x_offset_ratio"]) for eye in usable) / len(usable)
    y_offset = sum(float(eye["y_offset_ratio"]) for eye in usable) / len(usable)
    if x_offset <= -0.08:
        horizontal = "left"
    elif x_offset >= 0.08:
        horizontal = "right"
    else:
        horizontal = "front"
    if y_offset <= -0.14:
        vertical = "up"
    elif y_offset >= 0.18:
        vertical = "down"
    else:
        vertical = "level"
    confidence = min(0.98, 0.35 + min(abs(x_offset) / 0.18, 1.0) * 0.4 + min(len(usable) / 2, 1.0) * 0.23)
    return {
        "available": True,
        "method": "mediapipe_face_mesh_iris_offset",
        "direction": horizontal,
        "horizontal_direction": horizontal,
        "vertical_direction": vertical,
        "x_offset_ratio": round(x_offset, 5),
        "y_offset_ratio": round(y_offset, 5),
        "confidence": round(confidence, 4),
        "eye_count": len(usable),
        "eyes": [
            {
                "x_offset_ratio": round(float(eye["x_offset_ratio"]), 5),
                "y_offset_ratio": round(float(eye["y_offset_ratio"]), 5),
            }
            for eye in usable
        ],
    }


def head_pose_hint(landmarks: list[Any], width: int, height: int) -> dict[str, Any]:
    if len(landmarks) <= max(HEAD_POSE_POINTS):
        return {"available": False, "reason": "head pose landmarks unavailable"}
    nose = _point(landmarks, HEAD_POSE_POINTS[0], width, height)
    left_cheek = _point(landmarks, HEAD_POSE_POINTS[1], width, height)
    right_cheek = _point(landmarks, HEAD_POSE_POINTS[2], width, height)
    face_width = max(1.0, _distance(left_cheek, right_cheek))
    face_mid_x = (left_cheek[0] + right_cheek[0]) / 2
    yaw_ratio = (nose[0] - face_mid_x) / face_width
    if yaw_ratio <= -0.035:
        direction = "left"
    elif yaw_ratio >= 0.035:
        direction = "right"
    else:
        direction = "front"
    return {
        "available": True,
        "method": "nose_vs_cheek_center",
        "yaw_ratio": round(yaw_ratio, 5),
        "direction": direction,
    }


def extract_face_mesh_faces(frame: Any, face_mesh: Any | None) -> list[dict[str, Any]]:
    if face_mesh is None:
        return []
    height, width = frame.shape[:2]
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    result = face_mesh.process(rgb)
    raw_faces = getattr(result, "multi_face_landmarks", None) or []
    faces: list[dict[str, Any]] = []
    for raw_face in raw_faces:
        landmarks = list(raw_face.landmark)
        bbox = _landmark_bbox(landmarks, width, height)
        x1, y1, x2, y2 = [float(bbox[key]) for key in ("x1", "y1", "x2", "y2")]
        center_x = (x1 + x2) / 2
        center_y = (y1 + y2) / 2
        area_ratio = ((x2 - x1) * (y2 - y1)) / (width * height) if width and height else 0.0
        faces.append(
            {
                "bbox": bbox,
                "center": {"x": round(center_x, 2), "y": round(center_y, 2)},
                "center_ratio": [round(center_x / width, 4), round(center_y / height, 4)],
                "area_ratio": round(area_ratio, 5),
                "detector_direction": "mediapipe_face_mesh",
                "face_mesh": {
                    "available": True,
                    "landmark_count": len(landmarks),
                    "bbox": bbox,
                    "center_ratio": [round(center_x / width, 4), round(center_y / height, 4)],
                },
                "gaze": gaze_metrics(landmarks, width, height),
                "mouth": mouth_metrics(landmarks, width, height),
                "head_pose": head_pose_hint(landmarks, width, height),
            }
        )
    return faces
