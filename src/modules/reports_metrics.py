# src/modules/reports_metrics.py
"""Physiological metric calculators for Reports."""

import numpy as np


def calc_sprint_count(speed_kmh: np.ndarray, fps: float,
                      threshold_kmh: float = 20.0, min_gap_s: float = 1.0) -> int:
    """Counts sprints above threshold with a minimum gap between them."""
    above = (speed_kmh >= threshold_kmh).astype(np.int8)
    gap_frames = int(min_gap_s * fps)
    if not above.any():
        return 0

    # Rising / falling edges via diff on padded array
    padded  = np.concatenate(([0], above))
    d       = np.diff(padded)
    rising  = np.where(d == 1)[0]   # frame where each sprint starts
    falling = np.where(d == -1)[0]  # frame where each sprint ends

    if len(falling) < len(rising):
        falling = np.append(falling, len(speed_kmh))

    count    = 1
    prev_end = falling[0]
    for k in range(1, len(rising)):
        if rising[k] - prev_end >= gap_frames:
            count   += 1
            prev_end = falling[k] if k < len(falling) else len(speed_kmh)

    return count


# Tabela lookup para Yo-Yo Endurance (IE1 e IE2) — Bangsbo
# Chave: (nivel, shuttle) → VO2max
YOYO_ENDURANCE_TABLE = {
    (5,2):27.1,(5,4):28.0,(5,6):28.6,(5,9):29.9,
    (6,2):30.5,(6,4):31.4,(6,6):32.2,(6,9):33.2,
    (7,2):34.0,(7,4):34.6,(7,6):35.5,(7,8):36.1,(7,10):36.7,
    (8,2):37.5,(8,4):38.3,(8,6):39.1,(8,8):39.7,(8,10):40.6,
    (9,2):41.1,(9,4):41.6,(9,6):42.4,(9,8):43.0,(9,11):43.9,
    (10,2):44.4,(10,4):45.0,(10,6):45.7,(10,8):46.3,(10,11):47.4,
    (11,2):47.9,(11,4):48.5,(11,6):49.2,(11,8):49.9,(11,11):50.9,
    (12,2):51.4,(12,4):52.0,(12,6):52.6,(12,8):53.1,(12,10):53.7,(12,12):54.2,
    (13,2):54.9,(13,4):55.5,(13,6):56.0,(13,8):56.6,(13,10):57.1,(13,12):57.7,
    (14,2):58.1,(14,4):58.7,(14,6):59.2,(14,8):59.8,(14,10):60.4,(14,13):61.2,
    (15,2):61.7,(15,4):62.2,(15,6):62.8,(15,8):63.3,(15,10):63.9,(15,13):64.7,
    (16,2):65.2,(16,4):65.8,(16,6):66.3,(16,8):66.9,(16,10):67.4,(16,13):68.2,
    (17,2):68.7,(17,4):69.2,(17,6):69.8,(17,8):70.3,(17,10):70.9,(17,12):71.4,(17,14):72.0,
    (18,2):72.6,(18,4):73.1,(18,6):73.5,(18,8):74.2,(18,10):74.8,(18,12):75.3,(18,14):75.9,
    (19,2):76.4,(19,4):77.0,(19,6):77.6,(19,8):78.1,(19,10):78.6,(19,12):79.2,(19,15):80.0,
    (20,2):80.5,(20,4):81.1,(20,6):81.6,(20,8):82.1,(20,10):82.7,(20,12):83.2,(20,15):83.8,
}


def calc_vo2max(total_distance_m: float, age: int | None, sex: str | None,
                protocol: str = "ir1",
                endurance_level: int | None = None,
                endurance_shuttle: int | None = None) -> dict:
    """
    Calcula VO2max pelo protocolo Yo-Yo correto.

    protocol:
        "ir1" — Yo-Yo Intermittent Recovery Level 1 (mais comum, jovens/recreativos)
                Fórmula: dist × 0.0084 + 36.4  (Bangsbo et al. 2008)
        "ir2" — Yo-Yo Intermittent Recovery Level 2 (elite)
                Fórmula: dist × 0.0136 + 45.3  (Bangsbo et al. 2008)
        "endurance" — Yo-Yo Endurance IE1 ou IE2
                Lookup por nível:shuttle na tabela de Bangsbo
                Requer endurance_level e endurance_shuttle

    age e sex são buscados automaticamente do JSON de atletas pelo Reports.
    Classificação diferenciada por faixa etária e sexo.
    """
    warning = None

    # Calcular VO2max pelo protocolo
    if protocol == "ir1":
        vo2 = total_distance_m * 0.0084 + 36.4
        formula_label = "Yo-Yo IR1 — Bangsbo et al. (2008)"
    elif protocol == "ir2":
        vo2 = total_distance_m * 0.0136 + 45.3
        formula_label = "Yo-Yo IR2 — Bangsbo et al. (2008)"
    elif protocol == "endurance":
        if endurance_level is None or endurance_shuttle is None:
            return {"value": None, "classification": "—", "color": "#888888",
                    "warning": "Nível e shuttle necessários para Yo-Yo Endurance",
                    "formula": "Yo-Yo Endurance — Bangsbo"}
        # Lookup exato ou mais próximo
        key = (endurance_level, endurance_shuttle)
        if key in YOYO_ENDURANCE_TABLE:
            vo2 = YOYO_ENDURANCE_TABLE[key]
        else:
            # Interpolação linear com as chaves mais próximas
            keys = sorted(YOYO_ENDURANCE_TABLE.keys())
            lower = [k for k in keys if k <= key]
            upper = [k for k in keys if k >= key]
            if lower and upper:
                k1, k2 = lower[-1], upper[0]
                if k1 == k2:
                    vo2 = YOYO_ENDURANCE_TABLE[k1]
                else:
                    v1, v2 = YOYO_ENDURANCE_TABLE[k1], YOYO_ENDURANCE_TABLE[k2]
                    t = 0.5  # ponto médio como aproximação
                    vo2 = v1 + t * (v2 - v1)
                    warning = f"Nível {endurance_level}:{endurance_shuttle} interpolado"
            elif lower:
                vo2 = YOYO_ENDURANCE_TABLE[lower[-1]]
                warning = f"Nível {endurance_level}:{endurance_shuttle} aproximado"
            else:
                vo2 = YOYO_ENDURANCE_TABLE[upper[0]]
                warning = f"Nível {endurance_level}:{endurance_shuttle} aproximado"
        formula_label = "Yo-Yo Endurance — Bangsbo"
    else:
        return {"value": None, "classification": "—", "color": "#888888",
                "warning": f"Protocolo desconhecido: {protocol}", "formula": "—"}

    vo2 = round(vo2, 1)

    # Classificação por idade e sexo
    age_used = age if (age and age > 0) else 18
    sex_used = sex if sex in ("M", "F") else "M"

    if age is None or age <= 0:
        w = "idade não cadastrada (usando tabela adulto)"
        warning = (warning + " · " + w) if warning else w
    if sex not in ("M", "F"):
        w = "sexo não cadastrado (usando tabela masculina)"
        warning = (warning + " · " + w) if warning else w

    # Tabelas de referência por faixa etária e sexo
    if age_used < 18:
        thresholds = [(36.4,"Fraco"),(39.0,"Regular"),(42.0,"Bom"),(46.0,"Excelente")]
    elif sex_used == "F":
        thresholds = [(34.0,"Fraco"),(40.0,"Regular"),(47.0,"Bom"),(53.0,"Excelente")]
    else:
        thresholds = [(38.0,"Fraco"),(44.0,"Regular"),(51.0,"Bom"),(57.0,"Excelente")]

    classification = "Superior"
    for cutoff, label in thresholds:
        if vo2 < cutoff:
            classification = label
            break

    color_map = {
        "Fraco":     "#DC2626",
        "Regular":   "#D97706",
        "Bom":       "#16A34A",
        "Excelente": "#2563EB",
        "Superior":  "#7C3AED",
    }

    return {
        "value":          vo2,
        "classification": classification,
        "color":          color_map[classification],
        "warning":        warning,
        "formula":        formula_label,
    }


def calc_fatigue_index(speed_kmh: np.ndarray) -> dict:
    """
    fatigue = (mean_first_third - mean_last_third) / mean_first_third * 100
    Only considers moving frames (> 1 km/h) to avoid standing-still bias.
    Returns {"value": float, "color": str}.
    """
    moving = speed_kmh[speed_kmh > 1.0]
    n = len(moving)
    if n < 9:  # need at least 3 frames per third
        return {"value": 0.0, "color": "#16A34A"}
    third = n // 3
    first = float(np.nanmean(moving[:third]))
    last  = float(np.nanmean(moving[n - third:]))
    if first == 0:
        return {"value": 0.0, "color": "#16A34A"}
    value = (first - last) / first * 100.0
    value = round(value, 1)
    color = "#16A34A" if value < 10 else ("#D97706" if value < 20 else "#DC2626")
    return {"value": value, "color": color}
