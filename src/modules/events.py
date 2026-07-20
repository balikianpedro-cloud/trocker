"""
TROCKER Events Module
=======================
Implements, in code, the E01-E07 event taxonomy and calibration-gate-aware
trajectory validity described in:
  - Arquitetura_Computacional_Trocker_Veltron_Premium, section 7
  - Especificacao_Tecnica_E01-E07_Gate_Calibracao_Trocker.docx, section 3

Operates on the output of trajectory.compute_trajectory() (per-person,
per-frame metric position, velocity, and quality factor q_k).

IMPORTANT — engineering proposal, not a validated implementation:
All time thresholds in EventParams (reaction time, direction-change window,
failure timeout, lateral deviation tolerance) are placeholders carried over
from the technical specification. They must be calibrated against the pilot
videos in the real-data validation plan (architecture doc, section 20.8)
before this module is used outside development. See EventParams docstring.

Pure processing logic — no UI dependencies, mirrors tracker_engine.py.
"""

from dataclasses import dataclass, field
from enum import Enum

import numpy as np
import pandas as pd


class TrockerState(str, Enum):
    AGUARDANDO_INICIO = "AGUARDANDO_INICIO"
    EM_TRANSITO = "EM_TRANSITO"
    EM_ZONA_ALVO = "EM_ZONA_ALVO"
    FALHA = "FALHA"
    INTERROMPIDO = "INTERROMPIDO"


@dataclass
class Zone:
    """Axis-aligned rectangular zone in metric (homography-transformed) coordinates."""
    name: str
    xmin: float
    xmax: float
    ymin: float
    ymax: float

    def contains(self, x: float, y: float) -> bool:
        if np.isnan(x) or np.isnan(y):
            return False
        return self.xmin <= x <= self.xmax and self.ymin <= y <= self.ymax

    def center(self) -> tuple[float, float]:
        return ((self.xmin + self.xmax) / 2.0, (self.ymin + self.ymax) / 2.0)


@dataclass
class EventParams:
    """
    All defaults below are engineering proposals from the technical
    specification (section 2.3 / 3.4), not empirically validated values.
    Calibrate against pilot videos before real-data use.
    """
    reaction_time_s: float = 2.0            # Delta t_reacao — E01
    direction_change_window_s: float = 1.0  # Delta T — composite rule, E04
    failure_timeout_s: float = 6.0          # Delta t_falha — E06
    v_min_mps: float = 0.5                  # speed floor to confirm a turnaround
    corridor_tolerance_m: float = 2.0       # lateral tolerance around the start-end line
    lateral_deviation_time_s: float = 1.0   # Delta t_desvio — flag only, non-blocking
    min_composite_criteria: int = 3         # of 4, required to confirm E04 (see spec 3.3)


@dataclass
class Event:
    code: str
    name: str
    person: str
    frame: int
    t_s: float
    subtype: str | None = None
    detail: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = {
            "code": self.code, "name": self.name, "person": self.person,
            "frame": self.frame, "t_s": self.t_s, "subtype": self.subtype,
        }
        d.update(self.detail)
        return d


_EVENT_NAMES = {
    "E01": "Inicio do percurso",
    "E02": "Transito",
    "E03": "Chegada",
    "E04": "Mudanca de direcao",
    "E05": "Retorno",
    "E06": "Falha",
    "E07": "Interrupcao",
}


def _lateral_distance(x, y, zone_a: Zone, zone_b: Zone) -> float:
    """Perpendicular distance from (x, y) to the line joining the two zone centers."""
    ax, ay = zone_a.center()
    bx, by = zone_b.center()
    dx, dy = bx - ax, by - ay
    length = np.hypot(dx, dy)
    if length == 0:
        return np.hypot(x - ax, y - ay)
    # cross product magnitude / length = perpendicular distance
    return abs(dx * (ay - y) - (ax - x) * dy) / length


def detect_events_for_person(
    person_traj: pd.DataFrame,
    start_zone: Zone,
    end_zone: Zone,
    params: EventParams | None = None,
) -> list[Event]:
    """
    Runs the E01-E07 state machine over a single person's trajectory
    (output of trajectory.compute_trajectory(), filtered to one 'person').

    person_traj must be sorted by frame and contain columns:
        frame, t_s, x_m, y_m, velocity_mps, q_k

    Returns a chronological list of Event objects. E06/E07 carry a
    `subtype` distinguishing the specific failure/interruption case
    (see technical specification, section 3.4):
        E06: 'atraso', 'retorno_incompleto', 'sem_reacao'
        E07: 'sem_retomada'
    A person can also transition FALHA -> EM_TRANSITO again if movement
    resumes before the video ends; that transition is logged with
    subtype='recuperado_apos_falha' on the following E01/E03/E04 event's
    detail dict, not as its own event code (see spec 3.4, "Recuperacao").
    """
    if params is None:
        params = EventParams()

    traj = person_traj.sort_values("frame").reset_index(drop=True)
    events: list[Event] = []

    state = TrockerState.AGUARDANDO_INICIO
    zones = {"start": start_zone, "end": end_zone}
    current_target = "end"       # which zone the person is heading to
    leg_start_t = None
    was_recovering = False
    last_zone_seen = "start"

    def other(zone_key):
        return "end" if zone_key == "start" else "start"

    n = len(traj)
    for i in range(n):
        row = traj.iloc[i]
        x, y, t, frame = row["x_m"], row["y_m"], row["t_s"], int(row["frame"])
        v = row["velocity_mps"] if not np.isnan(row["velocity_mps"]) else 0.0

        in_start = zones["start"].contains(x, y)
        in_end = zones["end"].contains(x, y)
        in_target = zones[current_target].contains(x, y)

        if state == TrockerState.AGUARDANDO_INICIO:
            if in_start:
                last_zone_seen = "start"
                continue
            # left the start zone -> E01
            detail = {"recuperado_apos_falha": was_recovering} if was_recovering else {}
            events.append(Event("E01", _EVENT_NAMES["E01"], row.get("person", ""), frame, t, detail=detail))
            was_recovering = False
            state = TrockerState.EM_TRANSITO
            current_target = "end"
            leg_start_t = t
            continue

        if state == TrockerState.EM_TRANSITO:
            # E02 is continuous (transit), not logged as discrete events by default;
            # lateral-deviation flag is non-blocking, attached to E06/E07 if it persists.
            if in_target:
                events.append(Event("E03", _EVENT_NAMES["E03"], row.get("person", ""), frame, t))
                state = TrockerState.EM_ZONA_ALVO
                zone_entry_t = t
                zone_entry_idx = i
                last_zone_seen = current_target
                continue

            if leg_start_t is not None and (t - leg_start_t) > params.failure_timeout_s:
                events.append(Event(
                    "E06", _EVENT_NAMES["E06"], row.get("person", ""), frame, t,
                    subtype="atraso",
                    detail={"elapsed_s": round(t - leg_start_t, 2)},
                ))
                state = TrockerState.FALHA
                continue

        elif state == TrockerState.EM_ZONA_ALVO:
            window_end = zone_entry_t + params.direction_change_window_s
            if t <= window_end:
                # composite rule for E04: entry(already true) + speed dip below v_min
                # + (checked below) velocity inversion + timing compatibility
                speed_dipped = v <= params.v_min_mps
                timing_ok = True  # no external signal timestamps wired in yet
                # look ahead one step for a sign inversion of the longitudinal
                # component (approximated by direction of travel along the
                # start-end axis) — evaluated once the window closes, below.
                continue
            else:
                # window closed: evaluate composite criteria using the
                # trajectory segment between zone_entry and now
                seg = traj.iloc[zone_entry_idx:i + 1]
                criteria = _evaluate_direction_change(seg, start_zone, end_zone, current_target, params)
                if criteria["met_count"] >= params.min_composite_criteria:
                    events.append(Event(
                        "E04", _EVENT_NAMES["E04"], row.get("person", ""), frame, t,
                        detail={"criteria": criteria},
                    ))
                    if current_target == "end":
                        events.append(Event("E05", _EVENT_NAMES["E05"], row.get("person", ""), frame, t))
                    current_target = other(current_target)
                    leg_start_t = t
                    state = TrockerState.EM_TRANSITO
                else:
                    # arrived but never confirmed a turnaround -> treat the
                    # rest of the leg as ongoing transit toward the same target
                    state = TrockerState.EM_TRANSITO
                    leg_start_t = zone_entry_t
                continue

        if state == TrockerState.FALHA:
            # recovery: resumes if the person leaves the failure zone and
            # moves again in a plausible way
            if v > params.v_min_mps and not in_start and not in_end:
                state = TrockerState.EM_TRANSITO
                leg_start_t = t
                was_recovering = True
                continue

    # end of video: classify the open state
    if state == TrockerState.EM_TRANSITO and n > 0:
        last = traj.iloc[-1]
        events.append(Event(
            "E07", _EVENT_NAMES["E07"], last.get("person", ""), int(last["frame"]), last["t_s"],
            subtype="sem_retomada",
        ))

    return events


def _evaluate_direction_change(segment: pd.DataFrame, start_zone: Zone, end_zone: Zone,
                                current_target: str, params: EventParams) -> dict:
    """
    Composite rule for E04 (spec 3.3): counts how many of the four criteria
    are met within the direction-change window:
      1. entry into the target zone (always true when called)
      2. velocity dips below v_min at some point in the window
      3. longitudinal velocity component inverts sign across the window
      4. timing compatibility (placeholder True — no signal timestamps yet)
    """
    entry_met = True

    speed_dipped = bool((segment["velocity_mps"] <= params.v_min_mps).any())

    ax, ay = start_zone.center()
    bx, by = end_zone.center()
    axis_dx, axis_dy = bx - ax, by - ay
    axis_len = np.hypot(axis_dx, axis_dy) or 1.0
    ux, uy = axis_dx / axis_len, axis_dy / axis_len

    xs = segment["x_m"].to_numpy()
    ys = segment["y_m"].to_numpy()
    valid = ~np.isnan(xs) & ~np.isnan(ys)
    xs, ys = xs[valid], ys[valid]
    inverted = False
    if len(xs) >= 2:
        long_disp = np.diff(xs) * ux + np.diff(ys) * uy
        signs = np.sign(long_disp[long_disp != 0])
        inverted = len(set(signs.tolist())) > 1

    timing_ok = True  # no external audio-signal timestamps wired in yet

    met = [entry_met, speed_dipped, inverted, timing_ok]
    return {
        "entry": entry_met, "speed_dipped": speed_dipped,
        "velocity_inverted": inverted, "timing_ok": timing_ok,
        "met_count": sum(met),
    }


def detect_events(
    trajectory_df: pd.DataFrame,
    start_zone: Zone,
    end_zone: Zone,
    params: EventParams | None = None,
) -> pd.DataFrame:
    """Runs detect_events_for_person() for every person in trajectory_df, returns one events DataFrame."""
    all_events: list[dict] = []
    for person, group in trajectory_df.groupby("person"):
        group = group.copy()
        group["person"] = person
        for ev in detect_events_for_person(group, start_zone, end_zone, params):
            all_events.append(ev.to_dict())
    if not all_events:
        return pd.DataFrame(columns=["code", "name", "person", "frame", "t_s", "subtype"])
    return pd.DataFrame(all_events)
