# -*- coding: utf-8 -*-
"""Relatório final por POSIÇÃO a partir de um teste rastreado (json de trajetórias dos demos Yo-Yo / tiros) + planilha do
elenco (número no vídeo -> nome, posição, nascimento, altura, peso). Agrupamentos: '4' (GOL, DEF, MEI, ATA) ou
'5' (GOL, ZAG, LAT, MEI, ATA). Sai: xlsx (abas atletas, por_posicao, ranking), png (barras por posição) e md (resumo).
Uso: python position_report.py TRACKS.json ELENCO.csv SAIDA_DIR [--grupos 4|5] [--protocolo yoyo_ir1]
Sem planilha de elenco, gera o modelo ELENCO_modelo.csv para preencher.
"""
from __future__ import annotations
import sys, json
from pathlib import Path
import numpy as np, pandas as pd

MAPA_4 = {"GOL": "Goleiros", "ZAG": "Defesa", "LAT": "Defesa", "DEF": "Defesa", "MEI": "Meio-campo", "VOL": "Meio-campo", "ATA": "Ataque", "PON": "Ataque"}
MAPA_5 = {"GOL": "Goleiros", "ZAG": "Zagueiros", "LAT": "Laterais", "DEF": "Zagueiros", "MEI": "Meias", "VOL": "Meias", "ATA": "Atacantes", "PON": "Atacantes"}
ORDEM = {"4": ["Goleiros", "Defesa", "Meio-campo", "Ataque"], "5": ["Goleiros", "Zagueiros", "Laterais", "Meias", "Atacantes"]}


def tabela_atletas(tracks: dict, protocolo: str) -> pd.DataFrame:
    sys.path.insert(0, str(Path(__file__).parent)); from protocols import PROTOCOLOS, estimar
    p = PROTOCOLOS.get(protocolo); linhas = []
    for a in tracks["atletas"]:
        dist = float(a["dist"][-1]); perc = len(a["cruz"]) // 2; v = np.array(a["v"]); g = np.array(a["gaps"])
        niv = p.nivel_por_percurso(max(1, perc)).nivel if p and p.estagios else None
        vo2 = estimar(protocolo, dist_m=dist)["vo2max"] if protocolo in ("yoyo_ir1", "yoyo_ir2") else None
        # queda de rendimento: velocidade media CORRENDO (> 1,5 m/s) nos 20 % finais do teste vs 20 % iniciais
        idx = np.where((~g) & (v > 1.5))[0]; n = len(idx)
        fad = float(v[idx[int(0.8 * n):]].mean() / max(1e-6, v[idx[:int(0.2 * n)]].mean()) - 1) * 100 if n > 100 else None
        linhas.append(dict(atleta=a["id"], distancia_m=round(dist), percursos=perc, nivel=niv, vmax_kmh=round(float(np.percentile(v[~g], 99)) * 3.6, 1) if (~g).any() else None,
                           vo2max_est=vo2, cobertura_pct=round(100 * float(1 - g.mean())), queda_rendimento_pct=round(fad, 1) if fad is not None else None))
    return pd.DataFrame(linhas)


def _md_table(df: pd.DataFrame, index: bool = True) -> str:
    """Tabela Markdown sem depender de 'tabulate'."""
    try:
        return df.to_markdown(index=index)
    except Exception:
        return "```\n" + df.to_string(index=index) + "\n```"


def gerar_relatorio(df: pd.DataFrame, elenco=None, out_dir="." , grupos: str = "4", protocolo: str = "yoyo_ir1") -> dict:
    """Gera xlsx (atletas, por_posicao, ranking), png e md em out_dir.

    df: uma linha por atleta com pelo menos 'atleta', 'distancia_m', 'vmax_kmh'; opcionais: 'nome', 'posicao',
        'nivel', 'percursos', 'vo2max_est', 'cobertura_pct', 'queda_rendimento_pct', 'idade', 'sexo', 'peso_kg'.
    elenco: caminho de uma planilha (atleta;nome;posicao;nascimento;altura_cm;peso_kg) ou DataFrame, ou None
        quando 'nome' e 'posicao' já vêm em df (caso do app Trocker, cadastro em Athletes).
    Retorna dict com os caminhos gerados. Não troca o backend do matplotlib (o app usa QtAgg)."""
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    d = df.copy()
    if elenco is not None:
        e = elenco.copy() if isinstance(elenco, pd.DataFrame) else pd.read_csv(elenco, sep=None, engine="python")
        e.columns = [c.strip().lower() for c in e.columns]
        e["atleta"] = pd.to_numeric(e["atleta"], errors="coerce")
        d = d.drop(columns=[c for c in ("nome", "posicao") if c in d.columns and c in e.columns]).merge(e, on="atleta", how="left")
        if "nascimento" in d.columns and "idade" not in d.columns:
            nasc = pd.to_datetime(d["nascimento"], errors="coerce", dayfirst=True)
            d["idade"] = ((pd.Timestamp.today() - nasc).dt.days / 365.25).round(1)
    for col in ("nome", "posicao"):
        if col not in d.columns: d[col] = ""
    for col in ("nivel", "vo2max_est", "queda_rendimento_pct", "vmax_kmh"):
        if col not in d.columns: d[col] = np.nan
    d["posicao"] = d["posicao"].fillna("").astype(str).str.strip().str.upper().str[:3]
    mapa = MAPA_4 if grupos == "4" else MAPA_5
    d["grupo"] = d["posicao"].map(mapa).fillna("Não informada")
    # z-score dentro do elenco e percentil dentro do grupo
    for col in ("distancia_m", "vmax_kmh"):
        sd = d[col].std(ddof=0)
        d[f"z_{col}"] = ((d[col] - d[col].mean()) / sd).round(2) if sd and sd > 0 else 0.0
        d[f"percentil_grupo_{col}"] = d.groupby("grupo")[col].rank(pct=True).mul(100).round(0)
    resumo = d.groupby("grupo").agg(n=("atleta", "count"), distancia_media_m=("distancia_m", "mean"), distancia_max_m=("distancia_m", "max"),
                                    nivel_mediano=("nivel", "median"), vmax_media_kmh=("vmax_kmh", "mean"), vo2max_medio=("vo2max_est", "mean"),
                                    queda_rendimento_media_pct=("queda_rendimento_pct", "mean")).round(1)
    resumo = resumo.reindex([g for g in ORDEM[grupos] if g in resumo.index] + [g for g in resumo.index if g not in ORDEM[grupos]])
    rank_cols = ["atleta", "nome", "posicao", "grupo", "distancia_m", "nivel", "vmax_kmh", "vo2max_est", "z_distancia_m", "percentil_grupo_distancia_m"]
    rank = d.sort_values("distancia_m", ascending=False)[rank_cols]
    xlsx = out / "relatorio_por_posicao.xlsx"
    with pd.ExcelWriter(xlsx) as w:
        d.to_excel(w, sheet_name="atletas", index=False); resumo.to_excel(w, sheet_name="por_posicao"); rank.to_excel(w, sheet_name="ranking", index=False)
    png = out / "distancia_por_posicao.png"
    try:
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        from matplotlib.patches import Patch
        cores = dict(zip(ORDEM[grupos] + ["Não informada"], ["#C9A961", "#6680A6", "#2D5C62", "#E7E2D8", "#8A93A6", "#555555"]))
        fig = Figure(figsize=(12, 5)); FigureCanvasAgg(fig); ax = fig.add_subplot(111)
        dd = d.sort_values(["grupo", "distancia_m"], ascending=[True, False])
        ax.bar(range(len(dd)), dd.distancia_m, color=[cores.get(g, "#888") for g in dd.grupo])
        ax.set_xticks(range(len(dd))); ax.set_xticklabels([f"#{a}" for a in dd.atleta], fontsize=7)
        for g in resumo.index: ax.axhline(resumo.loc[g, "distancia_media_m"], color=cores.get(g, "#888"), lw=0.8, ls="--")
        ax.set_ylabel("distância (m)"); ax.set_title(f"{protocolo}: distância por atleta, cor = posição (linhas = média do grupo)", fontsize=10)
        ax.legend(handles=[Patch(color=cores[g], label=g) for g in resumo.index if g in cores], fontsize=8)
        fig.tight_layout(); fig.savefig(png, dpi=130)
    except Exception as ex:
        print("grafico:", ex); png = None
    md = [f"# Relatório por posição — {protocolo}", "", f"Atletas: {len(d)} | agrupamento: {grupos} grupos", "", _md_table(resumo), "",
          "## Ranking", "", _md_table(rank.head(30), index=False)]
    mdp = out / "relatorio_por_posicao.md"; mdp.write_text("\n".join(md), encoding="utf-8")
    return {"xlsx": str(xlsx), "png": str(png) if png else None, "md": str(mdp), "resumo": resumo, "atletas": d}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]; opts = dict(zip(sys.argv[1:-1:1], sys.argv[2::1]))
    grupos = opts.get("--grupos", "4"); protocolo = opts.get("--protocolo", "yoyo_ir1")
    tracks = json.load(open(args[0])); out = Path(args[2] if len(args) > 2 else "."); out.mkdir(parents=True, exist_ok=True)
    df = tabela_atletas(tracks, protocolo)
    elenco = Path(args[1]) if len(args) > 1 else None
    if elenco is None or not elenco.exists():
        modelo = out / "ELENCO_modelo.csv"
        pd.DataFrame(dict(atleta=df.atleta, nome="", posicao="", nascimento="", altura_cm="", peso_kg="")).to_csv(modelo, index=False, sep=";")
        print("planilha do elenco nao encontrada; modelo gerado para preencher (posicao: GOL/ZAG/LAT/MEI/ATA):", modelo)
        df.to_csv(out / "atletas_sem_posicao.csv", index=False, sep=";"); print(df.to_string(index=False)); return
    r = gerar_relatorio(df, elenco, out, grupos=grupos, protocolo=protocolo)
    print(r["resumo"].to_string()); print("->", r["xlsx"])


if __name__ == "__main__": main()
