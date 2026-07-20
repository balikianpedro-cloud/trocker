# src/modules/player_io.py
"""Shared I/O helpers for player name/profile JSON files."""

import os
import json


def players_json_path(project_path: str, video_path: str) -> str | None:
    """Returns the path to the players JSON for a given video."""
    if not project_path or not video_path:
        return None
    stem = os.path.splitext(os.path.basename(video_path))[0]
    base = stem[:-8] if stem.endswith("_tracked") else stem
    return os.path.join(project_path, "metadata", f"{base}_players.json")


def load_player_data(project_path: str, video_path: str) -> dict:
    """
    Loads the players JSON.
    Returns {int: {"name": str, "age": int|None, "sex": str|None, "weight": float|None}}.
    Compatible with old format {"1": "João"} and new {"1": {"name": "João", "age": 13, ...}}.
    """
    path = players_json_path(project_path, video_path)
    if not path or not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        result = {}
        for k, v in raw.items():
            mid = int(k)
            if isinstance(v, str):
                result[mid] = {"name": v, "age": None, "sex": None, "weight": None}
            elif isinstance(v, dict):
                result[mid] = {
                    "name":   v.get("name", f"p{mid}"),
                    "age":    v.get("age"),
                    "sex":    v.get("sex"),
                    "weight": v.get("weight"),
                }
            else:
                result[mid] = {"name": f"p{mid}", "age": None, "sex": None, "weight": None}
        return result
    except Exception:
        return {}


def save_player_data(project_path: str, video_path: str, data: dict) -> None:
    """
    Saves the player dict. Merges with existing file to preserve untouched fields.
    Always writes in the new extended format.
    """
    path = players_json_path(project_path, video_path)
    if not path:
        return
    existing = load_player_data(project_path, video_path)
    # Start from ALL existing athletes (load_player_data guarantees normalized format)
    merged = {str(mid): dict(profile) for mid, profile in existing.items()}
    # Overwrite only the athletes present in data
    for mid, profile in data.items():
        mid_str = str(int(mid))
        ex = merged.get(mid_str, {})
        merged[mid_str] = {
            "name":   profile.get("name",   ex.get("name",   f"p{mid}")),
            "age":    profile.get("age",    ex.get("age")),
            "sex":    profile.get("sex",    ex.get("sex")),
            "weight": profile.get("weight", ex.get("weight")),
        }
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)


def load_player_names(project_path: str, video_path: str) -> dict:
    """Shortcut: returns {int: str} with just names."""
    data = load_player_data(project_path, video_path)
    return {mid: profile["name"] for mid, profile in data.items()}


def save_player_names(project_path: str, video_path: str, names: dict) -> None:
    """Saves only names, preserving age/sex/weight already in the JSON."""
    existing = load_player_data(project_path, video_path)
    merged = {}
    for mid, name in names.items():
        mid_int = int(mid)
        ex = existing.get(mid_int, {})
        merged[mid_int] = {
            "name":   name,
            "age":    ex.get("age"),
            "sex":    ex.get("sex"),
            "weight": ex.get("weight"),
        }
    save_player_data(project_path, video_path, merged)
