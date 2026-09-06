# -*- coding: utf-8 -*-
"""Registro de protocolos de campo do Trocker: tabelas de estágio, distância por percurso e fórmulas de estimativa.
Todos os testes usam o MESMO motor de rastreio (detecção de pessoas + associação ótima + homografia); o que muda é
esta tabela. Fontes: Bangsbo, Iaia & Krustrup (2008) Sports Med 38:37-51 (Yo-Yo IR1/IR2); Buchheit (2008) JSCR 22:365-374
(30-15 IFT); Léger et al. (1988) J Sports Sci 6:93-101 e Léger & Gadoury (1989) (20 m multiestágio / endurance contínuo).
Estimativas de VO2max são LEITURAS DE DESEMPENHO para ranking e acompanhamento, não substituem ergoespirometria.
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class Estagio:
    nivel: int; velocidade_kmh: float; n_percursos: int


@dataclass
class Protocolo:
    codigo: str; nome: str; distancia_percurso_m: float; ida_e_volta: bool; recuperacao_s: float
    estagios: list[Estagio] = field(default_factory=list); referencia: str = ""; observacao: str = ""

    def nivel_por_percurso(self, n: int) -> Estagio:
        acc = 0
        for e in self.estagios:
            acc += e.n_percursos
            if n <= acc: return e
        return self.estagios[-1]

    def distancia_total(self, n_percursos: int) -> float:
        return n_percursos * self.distancia_percurso_m * (2 if self.ida_e_volta else 1)

    def total_percursos(self) -> int: return sum(e.n_percursos for e in self.estagios)


def _yoyo(codigo, nome, tabela, ref, obs=""):
    return Protocolo(codigo, nome, 20.0, True, 10.0, [Estagio(n, v, p) for n, v, p in tabela], ref, obs)


YOYO_IR1 = _yoyo("yoyo_ir1", "Yo-Yo Intermittent Recovery nível 1",
                 [(1, 10.0, 1), (2, 12.0, 1), (3, 13.0, 2), (4, 13.5, 3), (5, 14.0, 4), (6, 14.5, 8), (7, 15.0, 8), (8, 15.5, 8), (9, 16.0, 8), (10, 16.5, 8), (11, 17.0, 8), (12, 17.5, 8), (13, 18.0, 8)],
                 "Bangsbo et al. (2008)", "VO2max = 0,0084 x dist + 36,4")
YOYO_IR2 = _yoyo("yoyo_ir2", "Yo-Yo Intermittent Recovery nível 2",
                 [(1, 11.5, 1), (2, 15.0, 1), (3, 16.0, 2), (4, 16.5, 3), (5, 17.0, 4), (6, 17.5, 8), (7, 18.0, 8), (8, 18.5, 8), (9, 19.0, 8), (10, 19.5, 8), (11, 20.0, 8)],
                 "Bangsbo et al. (2008)", "VO2max = 0,0136 x dist + 45,3")
# 30-15 IFT: corridas de 30 s ida-e-volta em 40 m com 15 s de recuperacao; 8 km/h inicial, +0,5 km/h por estagio
IFT_30_15 = Protocolo("ift_30_15", "30-15 Intermittent Fitness Test", 40.0, True, 15.0,
                      [Estagio(k + 1, 8.0 + 0.5 * k, 1) for k in range(30)], "Buchheit (2008)",
                      "cada 'percurso' aqui = 1 estagio de 30 s; a distancia vem do rastreio, nao da tabela; VIFT = velocidade do ultimo estagio completo")
# Endurance continuo (20 m multiestagio / 'beep test'): 8,5 km/h inicial, +0,5 km/h por minuto, sem recuperacao
LEGER_20M = Protocolo("leger_20m", "Teste de 20 m multiestagio (endurance continuo)", 20.0, True, 0.0,
                      [Estagio(k + 1, 8.5 + 0.5 * k, 0) for k in range(21)], "Léger et al. (1988)",
                      "estagio de 1 min; numero de percursos por estagio depende da velocidade (calculado no motor); VO2max por idade e velocidade final")
YOYO_IE1 = Protocolo("yoyo_ie1", "Yo-Yo Intermittent Endurance nível 1", 20.0, True, 5.0, [], "Bangsbo",
                     "VO2max pela tabela de conversao de Bangsbo ja implementada em reports_metrics.calc_vo2max('endurance')")
SPRINT_30M = Protocolo("sprint_30m", "Tiros individuais de 30 m (parciais 10/20 m)", 30.0, False, 0.0, [], "-",
                       "tempo desde o inicio do movimento (sem fotocelula), parciais a cada 10 m, vmax; ver tiro1_analise.py")
SPRINT_20M = Protocolo("sprint_20m", "Tiros de 20 m em grupo (5 repeticoes)", 20.0, False, 0.0, [], "-",
                       "tempo 0-20 m, parcial 0-10 m, vmax, indice de fadiga entre repeticoes; ver tiros20_demo.py")
PROTOCOLOS = {p.codigo: p for p in (YOYO_IR1, YOYO_IR2, IFT_30_15, LEGER_20M, YOYO_IE1, SPRINT_30M, SPRINT_20M)}


def vo2max_yoyo_ir1(dist_m: float) -> float: return 0.0084 * dist_m + 36.4


def vo2max_yoyo_ir2(dist_m: float) -> float: return 0.0136 * dist_m + 45.3


def vo2max_ift(vift_kmh: float, idade_anos: float, peso_kg: float, sexo: str = "M") -> float:
    """Buchheit (2008): VO2max = 28,3 - 2,15 G - 0,741 A - 0,0357 W + 0,0586 A VIFT + 1,03 VIFT (G: 1 masc., 2 fem.)."""
    g = 1 if sexo.upper().startswith("M") else 2
    return 28.3 - 2.15 * g - 0.741 * idade_anos - 0.0357 * peso_kg + 0.0586 * idade_anos * vift_kmh + 1.03 * vift_kmh


def vo2max_leger(vel_final_kmh: float, idade_anos: float) -> float:
    """Léger et al. (1988) para 6-18 anos; adultos: Léger & Gadoury (1989)."""
    if idade_anos < 18: return 31.025 + 3.238 * vel_final_kmh - 3.248 * idade_anos + 0.1536 * idade_anos * vel_final_kmh
    return 6.0 * vel_final_kmh - 24.4


def estimar(protocolo: str, *, dist_m: float | None = None, nivel: int | None = None, vel_final_kmh: float | None = None,
            idade: float | None = None, peso: float | None = None, sexo: str = "M") -> dict:
    """Ponto unico de entrada: devolve {'vo2max', 'formula', 'aviso'} conforme o protocolo e os dados disponiveis."""
    p = PROTOCOLOS[protocolo]
    if protocolo == "yoyo_ir1" and dist_m is not None: return dict(vo2max=round(vo2max_yoyo_ir1(dist_m), 1), formula=p.observacao, aviso="")
    if protocolo == "yoyo_ir2" and dist_m is not None: return dict(vo2max=round(vo2max_yoyo_ir2(dist_m), 1), formula=p.observacao, aviso="")
    if protocolo == "ift_30_15":
        if None in (vel_final_kmh, idade, peso): return dict(vo2max=None, formula="Buchheit (2008)", aviso="30-15 IFT precisa de VIFT, idade e peso")
        return dict(vo2max=round(vo2max_ift(vel_final_kmh, idade, peso, sexo), 1), formula="Buchheit (2008)", aviso="")
    if protocolo == "leger_20m":
        if None in (vel_final_kmh, idade): return dict(vo2max=None, formula="Léger (1988)", aviso="20 m multiestagio precisa da velocidade final e da idade")
        return dict(vo2max=round(vo2max_leger(vel_final_kmh, idade), 1), formula="Léger (1988/1989)", aviso="")
    if protocolo == "yoyo_ie1":
        return dict(vo2max=None, formula="tabela Bangsbo (reports_metrics)", aviso="use reports_metrics.calc_vo2max(..., test_type='endurance', level=nivel, shuttle=percurso)")
    return dict(vo2max=None, formula="-", aviso=f"{p.nome}: sem estimativa de VO2max (teste de velocidade)")


if __name__ == "__main__":
    for c, p in PROTOCOLOS.items(): print(f"{c:12s} {p.nome:48s} percursos na tabela: {p.total_percursos():3d}  ref: {p.referencia}")
    print("IR1 21 percursos ->", YOYO_IR1.nivel_por_percurso(21), "dist", YOYO_IR1.distancia_total(21), "m ->", estimar("yoyo_ir1", dist_m=840))
    print("30-15 VIFT 18,5 km/h, 16 anos, 62 kg ->", estimar("ift_30_15", vel_final_kmh=18.5, idade=16, peso=62))
    print("Leger vel final 12,5 km/h, 15 anos ->", estimar("leger_20m", vel_final_kmh=12.5, idade=15))
