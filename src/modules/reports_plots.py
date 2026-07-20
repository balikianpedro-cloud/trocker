# src/modules/reports_plots.py
"""
Plot functions and constants extracted from reports.py.
Import from here to share between reports.py and future modules.
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.collections import LineCollection
from scipy.signal import savgol_filter
from scipy.ndimage import gaussian_filter


# =============================================================================
# CONSTANTS
# =============================================================================

MPL_LIGHT = {
    "figure.facecolor":  "#FFFFFF",
    "axes.facecolor":    "#FFFFFF",
    "axes.edgecolor":    "#CCCCCC",
    "axes.labelcolor":   "#1A1A1A",
    "axes.titlecolor":   "#111111",
    "axes.grid":         True,
    "grid.color":        "#EEEEEE",
    "grid.linewidth":    0.8,
    "grid.linestyle":    "--",
    "grid.alpha":        1.0,
    "xtick.color":       "#1A1A1A",
    "ytick.color":       "#1A1A1A",
    "text.color":        "#1A1A1A",
    "legend.facecolor":  "#FFFFFF",
    "legend.edgecolor":  "#CCCCCC",
    "legend.labelcolor": "#1A1A1A",
}

PLAYER_COLORS = [
    "#2563EB", "#16A34A", "#DC2626", "#D97706",
    "#7C3AED", "#DB2777", "#0891B2", "#65A30D",
    "#EA580C", "#9333EA", "#0D9488", "#B45309",
]

SPEED_ZONES = [
    (0,  7,  "#94A3B8", "Walk"),
    (7,  14, "#16A34A", "Jog"),
    (14, 21, "#D97706", "Run"),
    (21, 28, "#EA580C", "High Run"),
    (28, 999,"#DC2626", "Sprint"),
]

_LEGEND_KW = dict(fontsize=8, facecolor="white", edgecolor="#CCCCCC", labelcolor="#1A1A1A")


# =============================================================================
# PLAYER METRICS ENGINE
# =============================================================================

# Physiological max — above this is a tracking artefact
_MAX_SPEED_MS = 10.0   # 36 km/h


class PlayerMetrics:
    """Computes all metrics for one player from homography coordinates."""

    def __init__(self, marker_id: int, x: np.ndarray, y: np.ndarray,
                 fps: float, name: str = None):
        self.marker_id = marker_id
        self.name      = name or f"p{marker_id}"
        self.fps       = fps

        # --- Layer 1: limited interpolation (max 0.5 s gap) ---
        limit_frames = max(1, int(fps * 0.5))
        _interp_kw = dict(method="linear", limit_direction="forward")
        df_xy = pd.DataFrame({"x": x.astype(float), "y": y.astype(float)})
        df_xy = df_xy.interpolate(limit=limit_frames, **_interp_kw)
        xi, yi = df_xy["x"].values, df_xy["y"].values

        # --- Layer 2: remove teleports (speed > physiological limit) ---
        dx_raw    = np.diff(xi)
        dy_raw    = np.diff(yi)
        speed_raw = np.sqrt(dx_raw**2 + dy_raw**2) * fps  # m/s
        teleport_mask = speed_raw > _MAX_SPEED_MS
        if np.any(teleport_mask):
            bad_frames = np.where(teleport_mask)[0] + 1
            xi[bad_frames] = np.nan
            yi[bad_frames] = np.nan
            df_xy2 = pd.DataFrame({"x": xi, "y": yi})
            df_xy2 = df_xy2.interpolate(limit=3, **_interp_kw)
            xi, yi = df_xy2["x"].values, df_xy2["y"].values

        # Clean coords kept for distance (no smoothing bias)
        self._xi_clean = xi.copy()
        self._yi_clean = yi.copy()

        # --- Layer 3: Savitzky-Golay for speed/accel only ---
        window    = max(5, int(round(fps * 0.5)) | 1)
        polyorder = min(3, window - 1)
        xi_full = pd.Series(xi).ffill().bfill().values
        yi_full = pd.Series(yi).ffill().bfill().values
        self.x = savgol_filter(xi_full, window_length=window, polyorder=polyorder)
        self.y = savgol_filter(yi_full, window_length=window, polyorder=polyorder)

        self._compute()

    def _compute(self):
        # --- Distance: clean raw coords (preserves real reversals) ---
        dx_clean = np.diff(self._xi_clean)
        dy_clean = np.diff(self._yi_clean)
        dist_per_frame = np.sqrt(dx_clean**2 + dy_clean**2)
        self.total_distance = float(np.nansum(dist_per_frame))
        self.dist_per_frame = dist_per_frame

        # --- Speed/accel: smoothed coords ---
        dx = np.diff(self.x)
        dy = np.diff(self.y)
        dist_smooth    = np.sqrt(dx**2 + dy**2)
        self.speed_ms  = dist_smooth * self.fps
        self.speed_kmh = self.speed_ms * 3.6
        self.accel     = np.diff(self.speed_ms) * self.fps

        # --- Speed zones ---
        self.zone_times = {}
        for lo, hi, color, label in SPEED_ZONES:
            mask = (self.speed_kmh >= lo) & (self.speed_kmh < hi)
            self.zone_times[label] = float(np.sum(mask) / self.fps)

        # --- Summary metrics ---
        self.total_time    = float(len(self.x) / self.fps)
        self.avg_speed_kmh = float(np.nanmean(self.speed_kmh))
        # p95 — eliminates residual noise spikes
        self.max_speed_kmh = float(np.nanpercentile(self.speed_kmh, 95))
        self.avg_accel     = float(np.nanmean(self.accel))
        self.max_accel     = float(np.nanmax(self.accel))
        self.max_decel     = float(np.nanmin(self.accel))

        n = len(self.speed_ms)
        self.time_axis = np.arange(n) / self.fps


# =============================================================================
# STYLE HELPER
# =============================================================================

def _style_ax(ax, title, xlabel, ylabel, *, legend=True, legend_kw=None,
              grid_axis="both", clean_spines=False):
    ax.set_title(title, color="#111111", fontsize=12, fontweight="bold")
    ax.set_xlabel(xlabel, color="#1A1A1A", fontsize=9)
    ax.set_ylabel(ylabel, color="#1A1A1A", fontsize=9)
    ax.tick_params(labelsize=8, colors="#1A1A1A")
    if legend:
        ax.legend(**{**_LEGEND_KW, **(legend_kw or {})})
    ax.grid(True, color="#EEEEEE", linewidth=0.8, axis=grid_axis)
    if clean_spines:
        ax.spines[["top", "right"]].set_visible(False)
        ax.spines[["left", "bottom"]].set_color("#CCCCCC")


# =============================================================================
# PLOT FUNCTIONS
# =============================================================================

def plot_speed_over_time(players: list, ax, title="Speed Over Time"):
    ax.cla()
    ax.set_facecolor(MPL_LIGHT["axes.facecolor"])
    window = max(3, int(players[0].fps * 0.5))
    for i, p in enumerate(players):
        color  = PLAYER_COLORS[i % len(PLAYER_COLORS)]
        smooth = pd.Series(p.speed_kmh).rolling(window, center=True, min_periods=1).mean().values
        ax.plot(p.time_axis, smooth, color=color, linewidth=1.8, alpha=0.9, label=p.name)
    zone_refs = {"Jog": (7, SPEED_ZONES[1][2]), "Run": (14, SPEED_ZONES[2][2]),
                 "High Run": (21, SPEED_ZONES[3][2]), "Sprint": (28, SPEED_ZONES[4][2])}
    for lbl, (val, color) in zone_refs.items():
        ax.axhline(y=val, color=color, linewidth=0.8, linestyle="--", alpha=0.55)
        ax.text(0.01, val + 0.4, lbl, color="#555555", fontsize=7,
                va="bottom", transform=ax.get_yaxis_transform())
    _style_ax(ax, title, "Time (s)", "Speed (km/h)")


def plot_accel_over_time(players: list, ax, title="Acceleration Over Time"):
    ax.cla()
    ax.set_facecolor(MPL_LIGHT["axes.facecolor"])
    for i, p in enumerate(players):
        color = PLAYER_COLORS[i % len(PLAYER_COLORS)]
        t = p.time_axis[1:]
        ax.plot(t, p.accel, color=color, linewidth=1.2, alpha=0.8, label=p.name)
        ax.fill_between(t, p.accel, 0, where=(p.accel > 0), alpha=0.12, color="#16A34A")
        ax.fill_between(t, p.accel, 0, where=(p.accel < 0), alpha=0.12, color="#DC2626")
    ax.axhline(0, color="#888888", linewidth=0.9, linestyle="--")
    _style_ax(ax, title, "Time (s)", "Accel (m/s²)")


def plot_distance_over_time(players: list, ax, title="Cumulative Distance"):
    ax.cla()
    ax.set_facecolor(MPL_LIGHT["axes.facecolor"])
    for i, p in enumerate(players):
        color = PLAYER_COLORS[i % len(PLAYER_COLORS)]
        dist_cumsum = np.cumsum(p.dist_per_frame)
        ax.plot(p.time_axis, dist_cumsum, color=color, linewidth=1.8, label=p.name)
    _style_ax(ax, title, "Time (s)", "Distance (m)")


def plot_bar_comparison(players: list, metric: str, ylabel: str, title: str, ax):
    ax.cla()
    ax.set_facecolor(MPL_LIGHT["axes.facecolor"])
    names  = [p.name for p in players]
    values = [getattr(p, metric) for p in players]
    colors = [PLAYER_COLORS[i % len(PLAYER_COLORS)] for i in range(len(players))]
    bars = ax.bar(names, values, color=colors, alpha=0.88, width=0.6,
                  edgecolor="white", linewidth=0.8)
    vmax = max(abs(v) for v in values) if values else 1
    for bar, val in zip(bars, values):
        bar_h  = bar.get_height()
        offset = vmax * 0.025 if bar_h >= 0 else -vmax * 0.05
        va     = "bottom" if bar_h >= 0 else "top"
        ax.text(bar.get_x() + bar.get_width() / 2,
                bar_h + offset, f"{val:.1f}",
                ha="center", va=va, color="#1A1A1A", fontsize=9, fontweight="bold")
    ax.tick_params(axis="x", rotation=30, labelsize=9, colors="#1A1A1A")
    _style_ax(ax, title, "", ylabel, legend=False, grid_axis="y", clean_spines=True)
    if values:
        margin = vmax * 0.22
        lo = min(0, min(values)) - margin
        hi = max(0, max(values)) + margin
        ax.set_ylim(lo, hi)


def plot_zone_bars(players: list, ax, title="Time in Speed Zones"):
    ax.cla()
    ax.set_facecolor(MPL_LIGHT["axes.facecolor"])
    zone_labels = [z[3] for z in SPEED_ZONES]
    zone_colors = [z[2] for z in SPEED_ZONES]
    names       = [p.name for p in players]
    bottoms     = np.zeros(len(players))
    for label, color in zip(zone_labels, zone_colors):
        vals = np.array([p.zone_times.get(label, 0) for p in players])
        ax.bar(names, vals, bottom=bottoms, color=color,
               alpha=0.88, label=label, width=0.6, edgecolor="white", linewidth=0.5)
        bottoms += vals
    ax.tick_params(axis="x", rotation=30, labelsize=9, colors="#1A1A1A")
    _style_ax(ax, title, "", "Time (s)",
              legend_kw={"loc": "upper right"}, grid_axis="y", clean_spines=True)


def plot_trajectory(player: "PlayerMetrics", ax, title=None,
                    field_length=None, field_width=None):
    ax.cla()
    ax.set_facecolor("#F0F4F0")
    x, y  = player.x, player.y
    speed = np.concatenate([[0], player.speed_kmh])
    step  = max(1, len(x) // 2000)
    xi, yi, si = x[::step], y[::step], speed[::step]
    for lo, hi, color, label in SPEED_ZONES:
        mask = (si >= lo) & (si < hi)
        if not np.any(mask):
            continue
        segs = []
        for j in range(1, len(xi)):
            if mask[j]:
                segs.append([(xi[j-1], yi[j-1]), (xi[j], yi[j])])
        if segs:
            lc = LineCollection(segs, color=color, linewidth=2.5, alpha=0.9, capstyle="round")
            ax.add_collection(lc)
    ax.scatter([x[0]],  [y[0]],  color="#16A34A", s=60, zorder=5, label="Start")
    ax.scatter([x[-1]], [y[-1]], color="#DC2626", s=60, zorder=5, label="End")
    if field_length and field_width:
        rect = mpatches.Rectangle((0, 0), field_length, field_width,
                                   linewidth=1.5, edgecolor="#555555",
                                   facecolor="none", linestyle="--")
        ax.add_patch(rect)
    zone_patches = [mpatches.Patch(facecolor=c, edgecolor="none", label=lbl)
                    for _, _, c, lbl in SPEED_ZONES]
    ax.legend(handles=zone_patches, fontsize=6, facecolor="white",
              edgecolor="#CCCCCC", labelcolor="#1A1A1A",
              loc="upper right", handlelength=1.2, handleheight=0.8)
    _style_ax(ax, title or player.name, "X (m)", "Y (m)", legend=False, clean_spines=True)
    if field_length and field_width:
        ax.set_aspect("equal", adjustable="box")
        ax.set_xlim(0, field_length)
        ax.set_ylim(0, field_width)
    else:
        ax.autoscale()
        ax.set_aspect("equal", adjustable="datalim")


def plot_heatmap(player: "PlayerMetrics", ax, title=None,
                 field_length=None, field_width=None):
    ax.cla()
    ax.set_facecolor("#F8F8F8")
    x, y = player.x, player.y
    h, xedges, yedges = np.histogram2d(x, y, bins=60)
    h = gaussian_filter(h.T, sigma=1.5)
    extent = [xedges[0], xedges[-1], yedges[0], yedges[-1]]
    ax.imshow(h, extent=extent, origin="lower", aspect="auto",
              cmap="hot", interpolation="bilinear")
    if field_length and field_width:
        rect = mpatches.Rectangle((0, 0), field_length, field_width,
                                   linewidth=1.5, edgecolor="#444444",
                                   facecolor="none", linestyle="--")
        ax.add_patch(rect)
    _style_ax(ax, title or player.name, "X (m)", "Y (m)", legend=False, clean_spines=True)
    ax.set_aspect("equal", adjustable="box")
    if field_length and field_width:
        ax.set_xlim(0, field_length)
        ax.set_ylim(0, field_width)
