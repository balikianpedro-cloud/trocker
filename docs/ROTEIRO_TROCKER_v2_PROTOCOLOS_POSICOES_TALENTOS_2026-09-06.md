# Trocker v2 — protocolos, relatório por posição, potencial de jovens e operação no desk HP

Roteiro escrito em 06/09/2026 a partir do que foi construído e validado nos demos de 05–06/09 (Yo-Yo nadir e oblíquo,
tiros de 20 m e 30 m, elenco inteiro do Alagoano sub-17). Responde às cinco perguntas de Pedro Balikian Jr.

## 1. Outros protocolos: o motor é o mesmo, muda a tabela

O rastreio (detecção de pessoas + associação ótima + homografia do chão + cruzamento de linhas) não sabe qual teste
está sendo feito. O protocolo entra como uma tabela: distância entre as linhas, ida-e-volta ou não, recuperação, lista de
estágios e fórmula de estimativa. Isso já está implementado em `src/modules/protocols.py`:

| Protocolo | Linhas | Estágios | Estimativa | O que o vídeo precisa ter |
|---|---|---|---|---|
| Yo-Yo IR1 (temos) | 20 m, ida e volta, 10 s | tabela Bangsbo | 0,0084 x dist + 36,4 | duas linhas de cones a 20 m |
| Yo-Yo IR2 | 20 m | tabela Bangsbo | 0,0136 x dist + 45,3 | idem |
| Yo-Yo Endurance IE1/IE2 | 20 m, 5 s | tabela | tabela de conversão de Bangsbo (`reports_metrics.calc_vo2max`) | idem |
| 30-15 IFT | 40 m, 30 s corrida / 15 s pausa, +0,5 km/h por estágio | gerada | Buchheit 2008 (VIFT, idade, peso, sexo) | duas linhas a 40 m (zona de 3 m em cada ponta) |
| 20 m multiestágio contínuo (endurance) | 20 m, +0,5 km/h por minuto | gerada | Léger 1988 (velocidade final e idade) | duas linhas a 20 m |
| Tiros 20 m x 5 (temos) | 20 m, uma direção | – | tempo, parcial 10 m, vmax, fadiga | 4 cones nas pontas |
| Tiros 30 m com parciais (temos) | 30 m, uma direção | – | tempo, parciais 10/20 m, vmax | cones a cada 10 m |

O que o motor precisa saber por gravação: (a) posição das linhas de cones ou das linhas do campo para a escala;
(b) o protocolo; (c) para 30-15 e Léger: idade e peso de cada atleta (planilha do elenco). O "nível alcançado" vem
dos cruzamentos de linha do próprio atleta, não do áudio do teste; a velocidade-alvo da tabela serve para exibição.

Já gravados e ainda não processados: 30-15 e endurance, se estiverem nos vídeos catalogados em `TROCKER TODOS`.
Basta indicar qual arquivo é qual protocolo.

## 2. Relatório final por posição: sim, com uma planilha de elenco

`src/modules/position_report.py` lê o json de trajetórias de qualquer teste e uma planilha de elenco
(`atleta;nome;posicao;nascimento;altura_cm;peso_kg`, posição em GOL/ZAG/LAT/MEI/ATA) e produz:

- **Aba atletas:** distância, percursos, nível, vmax, VO2 estimado, cobertura de rastreio, queda de rendimento, idade,
  z-score no elenco e percentil dentro da própria posição.
- **Aba por_posicao:** n, distância média e máxima, nível mediano, vmax e VO2 médios, queda de rendimento média.
- **Ranking**, gráfico de barras colorido por posição com a média de cada grupo, e resumo em Markdown.
- Dois agrupamentos: `--grupos 4` (Goleiros, Defesa, Meio-campo, Ataque) ou `--grupos 5` (Goleiros, Zagueiros,
  Laterais, Meias, Atacantes). A escolha é um parâmetro, o cálculo é o mesmo.

O único trabalho manual é ligar o número do atleta no vídeo ao nome: a ordem na linha de largada é a mais prática
(o modelo `ELENCO_modelo.csv` já sai com os números na ordem da raia, da esquerda para a direita). Leitura de número
de camisa por OCR fica para uma etapa seguinte. O modelo para o Yo-Yo do sub-17 (26 atletas) já está em
`07_RESULTADOS_E_LAUDOS_ATLETAS/ENGINE AI/YOYO_SUB17_ELENCO_2025_DEMO/relatorio_posicao/`.

## 3. Jovens e identificação de potencial: proposta

O que dá para afirmar com dados de vídeo e sem exame: **quem rende mais do que o esperado para a idade e a maturação**
em capacidades que o futebol exige. Não é diagnóstico nem previsão de carreira; é uma triagem objetiva e repetível
para a comissão decidir em quem investir atenção. Proposta em três camadas:

**Camada 1, já possível com o que existe: Índice de Potencial Veltron (IPV), transparente.**
Cinco dimensões, cada uma como percentil dentro da mesma faixa etária (não do elenco misto):
1. Resistência intermitente: distância no Yo-Yo IR1 (ou nível no 30-15).
2. Velocidade: melhor tempo de 30 m e vmax.
3. Aceleração: parcial de 0–10 m.
4. Repetição: índice de fadiga nos tiros repetidos (20 m x 5).
5. Mudança de direção: tempo de virada no Yo-Yo, extraído da trajetória (desaceleração antes da linha e
   reaceleração depois), métrica que só o rastreio por vídeo entrega sem equipamento.

IPV = média dos percentis, com ajuste de maturação quando houver data de nascimento, altura e altura sentada
(offset de maturação de Mirwald 2002): atletas de maturação tardia com percentil alto recebem sinalização de
"potencial acima da maturação"; atletas de maturação precoce com percentil alto recebem "confirmar após maturação".
Isso combate o efeito da idade relativa, que é o maior viés conhecido na seleção de jovens.

**Camada 2, em 6 a 12 meses: acompanhamento longitudinal.** Repetir os testes a cada 8–12 semanas e olhar a
inclinação da curva por atleta, não só o valor. Quem melhora mais rápido que o grupo na mesma idade é um sinal mais
forte do que uma medida isolada.

**Camada 3, quando houver base: modelo estatístico.** Só faz sentido quando existirem algumas centenas de atletas
com desfecho registrado (convocação, contrato, permanência na base 2 anos depois). Aí um modelo simples
(regressão logística ou gradient boosting) pode pesar as dimensões. A metabolômica do CRB 2022 (ACWR x metabólitos)
é candidata a entrar como camada de estado interno nesse estágio, não antes.

Salvaguardas: consentimento dos responsáveis, LGPD (menores), relatório sem vocabulário clínico, e nunca um rótulo
binário "talento / não talento": sempre percentil, maturação e tendência.

## 4. Software Trocker: onde estamos e o que entra agora

O aplicativo já existe (`src/main.py`, PySide6/QML; módulos de detecção YOLO11, ByteTrack/BotSort, homografia,
PlayerMetrics, VO2 por Bangsbo). O que os demos desta semana acrescentam e que ainda não está no app:

1. **Motor de campo sem intervenção:** raias automáticas, associação ótima (Hungarian) em metros, caixa oculta
   quando não há detecção, contagem automática de percursos e nível (hoje só nos scripts de `veltron-demos`).
2. **Calibração em três modos:** nadir por duas linhas de cones; oblíquo por 4 cones nas pontas; oblíquo por linhas
   do campo + estabilização quadro a quadro (`estab_campo.py`), que foi o que resolveu o elenco inteiro.
3. **Protocolos como dados** (`protocols.py`) e **relatório por posição** (`position_report.py`), já no repositório.
4. **Filtro de uniforme** para excluir comissão e auxiliares do rastreio.
5. **Tiros individuais com cronômetro automático** (largada pelo movimento, parciais).

Ordem de integração sugerida (cada item é uma tela ou um botão no app):
1. `tracker_engine`: adicionar o modo "teste de campo" chamando o motor dos demos (detecção → csv → análise → json).
2. Tela de calibração com os três modos e o gate de erro de reprojeção (já existe em `homography_module`).
3. Seletor de protocolo (lê `PROTOCOLOS`) e planilha de elenco (posições, nascimento, peso).
4. Relatório: por atleta, por posição, e o IPV quando houver faixa etária.
5. Exportação: vídeo anotado (render dos demos), xlsx, PDF.

## 5. Como rodar tudo no desk HP

Pacote pronto em `00_FERRAMENTAS/veltron-demos/HP_SETUP/` (LEIA-ME_HP.md, setup_hp.ps1, environment_trocker.yml,
checar_ambiente.py, ajustar_caminhos.py). Sequência: driver NVIDIA → Miniconda → `setup_hp.ps1` → `ajustar_caminhos.py` (os vídeos TROCKER TODOS já chegam pelo OneDrive, em 10_VIDEOS_E_AUDIOS) → `checar_ambiente.py` = PRONTO. Depois, um teste por vez:
detecção (GPU) → análise (CPU, 1 min) → render (CPU, 5–15 min). Com a GPU do desk sem limitação térmica, um
Yo-Yo de 7 min deve levar menos de 15 minutos de ponta a ponta.
