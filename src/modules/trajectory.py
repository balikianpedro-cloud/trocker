"""
TROCKER Trajectory Module
==========================
Reconstructs filtered metric trajectories, displacement, and valid distance
from a homography-transformed tracking CSV (output of
homography_module.apply_homography / preselected_homography).

Implements, in code, the trajectory reconstruction described in the
architecture document (Arquitetura_Computacional_Trocker_Veltron_Premium,
sections 6 and 20.1/24): median filtering, velocity-based plausibility
rejection, and quality-weighted valid distance (Equations 2-4).

Pure processing logic — no UI dependencies, mirrors tracker_engine.py.
"""

import numpy as np
import pandas as pd


def _person_ids(df: pd.DataFrame) -> list[str]:
    """Column prefixes for tracked persons, e.g. 'p1', 'p2', ... from p1_x/p1_y pairs."""
    ids = []
    for col in df.columns:
        if col.endswith('_x'):
            base = col[:-2]
            if f'{base}_y' in df.columns:
                ids.append(base)
    return ids


def _median_filter_1d(values: np.ndarray, window: int) -> np.ndarray:
    """
    Rolling median filter that tolerates NaNs (missing detections) without
    propagating them further than necessary. window must be odd; even
    values are incremented by 1.
    """
    if window < 1:
        return values.copy()
    if window % 2 == 0:
        window += 1
    n = len(values)
    half = window // 2
    out = np.full(n, np.nan)
    for i in range(n):
        lo = max(0, i - half)
        hi = min(n, i + half + 1)
        segment = values[lo:hi]
        valid = segment[~np.isnan(segment)]
        if len(valid) > 0:
            out[i] = np.median(valid)
    return out


def compute_trajectory(
    df_homography: pd.DataFrame,
    fps: float,
    median_window: int = 5,
    v_max_mps: float = 10.0,
) -> pd.DataFrame:
    """
    Reconstructs, for every tracked person in df_homography (a homography-
    transformed CSV in meters — see homography_module.apply_homography),
    a filtered trajectory with displacement, velocity, a per-step quality
    factor q_k, and cumulative valid distance.

    Parameters
    ----------
    df_homography : DataFrame with a 'frame' column and, per tracked
        person, a '{id}_x' / '{id}_y' column pair in meters.
    fps : video frame rate, used to convert frame deltas to seconds.
    median_window : odd window size (frames) for the median filter applied
        to x/y before computing displacement. Reduces jitter and false
        deltas from detection noise (architecture doc, section 6).
    v_max_mps : velocity implausibility threshold. Steps implying a speed
        above this are rejected (q_k = 0) rather than counted as valid
        displacement. Default is an engineering placeholder (10 m/s) — must
        be calibrated per protocol/age category before real-data use
        (see architecture doc, section 20.8).

    Returns
    -------
    DataFrame, one row per (person, frame), with columns:
        person, frame, t_s, x_m, y_m, dx_m, dy_m, displacement_m,
        velocity_mps, q_k, valid_displacement_m, cumulative_distance_m
    """
    if fps <= 0:
        raise ValueError("fps must be > 0")

    frames = df_homography['frame'].to_numpy()
    dt = 1.0 / fps

    rows = []
    for person in _person_ids(df_homography):
        x_raw = df_homography[f'{person}_x'].to_numpy(dtype=float)
        y_raw = df_homography[f'{person}_y'].to_numpy(dtype=float)

        x_filt = _median_filter_1d(x_raw, median_window)
        y_filt = _median_filter_1d(y_raw, median_window)

        n = len(frames)
        dx = np.full(n, np.nan)
        dy = np.full(n, np.nan)
        disp = np.full(n, np.nan)
        vel = np.full(n, np.nan)
        q_k = np.zeros(n)
        cumulative = 0.0
        cumulative_arr = np.zeros(n)

        for i in range(n):
            if i == 0 or np.isnan(x_filt[i]) or np.isnan(y_filt[i]):
                cumulative_arr[i] = cumulative
                continue
            if np.isnan(x_filt[i - 1]) or np.isnan(y_filt[i - 1]):
                cumulative_arr[i] = cumulative
                continue

            dx_i = x_filt[i] - x_filt[i - 1]
            dy_i = y_filt[i] - y_filt[i - 1]
            d_i = float(np.hypot(dx_i, dy_i))
            frame_gap = frames[i] - frames[i - 1]
            dt_i = dt * max(frame_gap, 1)
            v_i = d_i / dt_i if dt_i > 0 else np.inf

            dx[i] = dx_i
            dy[i] = dy_i
            disp[i] = d_i
            vel[i] = v_i

            valid = v_i <= v_max_mps
            q_k[i] = 1.0 if valid else 0.0
            if valid:
                cumulative += d_i
            cumulative_arr[i] = cumulative

        rows.append(pd.DataFrame({
            'person': person,
            'frame': frames,
            't_s': frames * dt,
            'x_m': x_filt,
            'y_m': y_filt,
            'dx_m': dx,
            'dy_m': dy,
            'displacement_m': disp,
            'velocity_mps': vel,
            'q_k': q_k,
            'valid_displacement_m': disp * q_k,
            'cumulative_distance_m': cumulative_arr,
        }))

    if not rows:
        return pd.DataFrame(columns=[
            'person', 'frame', 't_s', 'x_m', 'y_m', 'dx_m', 'dy_m',
            'displacement_m', 'velocity_mps', 'q_k', 'valid_displacement_m',
            'cumulative_distance_m',
        ])
    return pd.concat(rows, ignore_index=True)


def save_trajectory_csv(df_homography: pd.DataFrame, fps: float, output_path: str,
                         median_window: int = 5, v_max_mps: float = 10.0) -> pd.DataFrame:
    """Computes the trajectory and writes it to output_path as CSV. Returns the DataFrame."""
    traj = compute_trajectory(df_homography, fps, median_window=median_window, v_max_mps=v_max_mps)
    traj.to_csv(output_path, index=False)
    return traj
