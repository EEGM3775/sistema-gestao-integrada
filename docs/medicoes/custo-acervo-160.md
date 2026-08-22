# Custo de conversão por arquivo — acervo de 159 DWGs

> **Natureza: medição.** Uma passada, uma data, um corpus. O **desenho** do
> medidor está na [planta §4.7](../modulos/moduloprancheta.md#47-medir-o-custo-de-um-arquivo--e-as-três-vezes-em-que-medimos-outra-coisa);
> o histórico do defeito que ele corrige, no [D82](../historico-correcoes.md).

Gerado por [relatorio_custo_por_caminho.py](../../ferramentas/medicao/relatorio_custo_por_caminho.py) sobre
a obra 12 (pasta `acervo-corpus-160`), a partir do que o **pipeline de produção** gravou em
`DerivadaProjeto.memoria["custo"]`. Nada foi reprocessado para produzir esta tabela.

## Como ler

Cada linha é **um arquivo**, não uma conversão — um DWG rende duas (a prancha e a
miniatura), e às vezes mais, quando tem várias folhas.

| Coluna | O que é | O que **não** é |
|---|---|---|
| **Pico** | o custo da operação: `memory.peak` do cgroup quando há um, senão o maior das duas colunas de amostragem | não é a soma das duas metades quando a fonte é amostragem — é **piso**, e a coluna `Fonte` diz qual dos dois casos é |
| **Fonte** | `cgroup` (exato, pai e filho no mesmo instante) ou `amostragem` (piso, a 50 ms) | — |
| **Pico subproc.** | maior RSS do `dwg2dxf`, lido no `VmHWM` do `/proc` **dele** | não é marca d'água acumulada, e não conta memória herdada do pai no `fork` — foi o [D82](../historico-correcoes.md) |
| **Pico em proc.** | maior VA da janela da conversão, menos a linha de base | não é o pico do worker, que converte centenas de arquivos no mesmo processo |
| **CPU** / **Relógio** | somados entre as conversões do arquivo | tempo se soma; **memória não** |
| **MB/MB** | pico sobre peso de entrada | — |
| `n/d` | não medido: subprocesso mais curto que a amostragem, e sem cgroup | **não é zero.** Zero se leria como "não custou nada" |

**Memória não se soma; tempo sim.** As conversões rodaram em série **e com
`--concurrency 1`**, então os picos nunca existiram ao mesmo tempo: o que
dimensiona a máquina é o **maior**, não a soma. Isso é propriedade do deploy, não
da medição — com dois processos de conversão simultâneos, dois picos coexistem e
a conta muda.

## O acervo inteiro

| | |
|---|---|
| arquivos | **159** |
| entrada | **348.8 MB** |
| CPU somada | **805 s** |
| relógio somado | **810 s** |
| **pico de um arquivo — o maior** | **2.437 MB** |
| **pico de um arquivo — a mediana (só os medidos)** | **32 MB** |
| pico medido em | 83 de 159 arquivos |
| destes, por cgroup (exatos) | 0 |

**A distância entre a mediana e o maior é o resultado.** Um acervo destes é barato
na média e caro na cauda: dimensionar o worker pela mediana derruba a conversão de
um punhado de arquivos, e dimensionar pelo maior paga folga ociosa em quase todos.

**A mediana é dos arquivos medidos, e a distinção não é preciosismo.** Contar como
zero o arquivo que não foi medido faz a mediana descrever a *cobertura do medidor*
em vez do *custo do acervo* — e foi exatamente o que a primeira versão desta
tabela publicou.

## Por arquivo

Ordenado pelo pico — o mais caro primeiro.

| # | Caminho no acervo | Entrada | Pico | Fonte | Pico subproc. | Pico em proc. | CPU | Relógio | MB/MB | Veredito |
|--:|---|--:|--:|---|--:|--:|--:|--:|--:|---|
| 1 | `Projetos/Camaçari/Sandro Roberto/J2 - S_PROJETO EXECUTIVO FINAL COM LAZER.dwg` | 64.9 MB | ≥ 2.437 MB | amostragem | 2.437 MB | 0 MB | 13.5 s | 21.9 s | 38× | ⛔ recurso_excedido + miniatura |
| 2 | `Estudos/UFRB/Eng. Civil/TCC/TCC Escrito/imagens/Sensor de Incendio.dwg` | 9.4 MB | 1.577 MB | amostragem | 1.577 MB | 0 MB | 25.5 s | 24.1 s | 168× | ✅ prancha |
| 3 | `Documentos/Doc Edison/2024_05_20__11_18_29/557581198927/Attach/Media/WhatsApp Documents/ESGOTO 2023.dwg` | 16.2 MB | 920 MB | amostragem | 470 MB | 920 MB | 54.8 s | 54.6 s | 57× | ✅ prancha |
| 4 | `Projetos/Santo Antonio de Jesus/Jorge Galvâo/Projeto Predio Luciano/Estrutural/Imp/FILE.DWG` | 11.1 MB | 767 MB | amostragem | 441 MB | 767 MB | 32.6 s | 32.4 s | 69× | ✅ prancha |
| 5 | `Documentos/Doc Edison/2024_05_20__11_18_29/557581198927/Attach/Media/WhatsApp Documents/Sent/01 LOTEAMENTO PORTAL RESIDENCE.dwg` | 16.0 MB | 759 MB | amostragem | 428 MB | 759 MB | 38.4 s | 38.2 s | 47× | ✅ prancha |
| 6 | `Documentos/Doc Edison/2024_05_20__11_18_29/557581198927/Attach/Media/WhatsApp Documents/Loteamento Park Ville R8.dwg` | 14.2 MB | 652 MB | amostragem | 319 MB | 652 MB | 67.5 s | 67.2 s | 46× | ✅ prancha |
| 7 | `Projetos/Santo Antonio de Jesus/Taluma Cons/Portal Residence II/Memorial Descritivo Lotes/03 - Memorial de Lotes.dwg` | 12.8 MB | 596 MB | amostragem | 312 MB | 596 MB | 28.3 s | 28.1 s | 47× | ✅ prancha |
| 8 | `Documentos/Doc Edison/2024_05_20__11_18_29/557581198927/Attach/Media/WhatsApp Documents/Sent/DRENAGEM E ESOTO VICINAL 31_10 2023.dwg` | 10.3 MB | 412 MB | amostragem | 347 MB | 412 MB | 28.2 s | 28.0 s | 40× | ✅ prancha |
| 9 | `Projetos/Aratuipe/Passarela/FILE.DWG` | 7.7 MB | 386 MB | amostragem | 307 MB | 386 MB | 21.1 s | 23.8 s | 50× | ✅ prancha |
| 10 | `Estudos/UFRB/Eng. Civil/TCC/anexos sipef/ANEXO II Projetos/PROJETOS COMPLEMENTARES/ELÉTRICA/UFRB-CTC-ELE-PE-002-IF-1ºA-R02.dwg` | 3.2 MB | 318 MB | amostragem | 94 MB | 318 MB | 38.2 s | 38.1 s | 100× | ✅ prancha |
| 11 | `File.dwg` | 5.8 MB | 309 MB | amostragem | 228 MB | 309 MB | 19.0 s | 18.9 s | 53× | ✅ prancha |
| 12 | `Documentos/Doc Edison/2024_05_20__11_18_29/557581198927/Attach/Media/WhatsApp Documents/LEVANTAMENTO DE MATERIAIS-BLOCOS.dwg` | 9.1 MB | 309 MB | amostragem | 222 MB | 309 MB | 39.0 s | 38.8 s | 34× | ✅ prancha |
| 13 | `460017387_PES1_VOL_1_FLOCODEC_01A06_R04.dwg` | 6.9 MB | 301 MB | amostragem | 153 MB | 301 MB | 15.6 s | 15.5 s | 43× | ✅ prancha |
| 14 | `Documentos/Doc Edison/2024_05_20__11_18_29/557581198927/Attach/Media/WhatsApp Documents/JAMYLLE E PAULO_plantas executivas_R03.dwg` | 9.6 MB | 230 MB | amostragem | 230 MB | 161 MB | 53.7 s | 53.4 s | 24× | ✅ prancha |
| 15 | `Projetos/Santo Antonio de Jesus/Rycart/Embasa/Estacao Elevatoria/02 - IMP ESTRUTURA LAB E CONT EMBASA.DWG` | 8.5 MB | 181 MB | amostragem | 181 MB | 136 MB | 29.2 s | 29.0 s | 21× | ✅ prancha |
| 16 | `Documentos/Doc Edison/2024_05_20__11_18_29/557581198927/Attach/Media/WhatsApp Documents/Sent/CASA DA SOPA.dwg` | 7.4 MB | 180 MB | amostragem | 180 MB | 94 MB | 13.2 s | 13.1 s | 24× | ✅ prancha |
| 17 | `Documentos/Doc Edison/2024_05_20__11_18_29/557581198927/Attach/Media/WhatsApp Documents/PROJETO_NOVO_11_04_2024.dwg` | 3.8 MB | 151 MB | amostragem | 151 MB | 146 MB | 30.3 s | 30.2 s | 39× | ✅ prancha |
| 18 | `Projetos/Santo Antonio de Jesus/Taluma Cons/Portal Residence I/Projeto E Memorial Atualizados/Imagens Para F/Desenho1.dwg` | 24.6 MB | 125 MB | amostragem | 109 MB | 125 MB | 3.9 s | 3.8 s | 5× | ✅ prancha |
| 19 | `Projetos/Santo Antonio de Jesus/Taluma Cons/Portal Residence I/Praças/PRAÇA AVENIDA 01_10_2020.dwg` | 3.5 MB | 116 MB | amostragem | 116 MB | 22 MB | 12.2 s | 12.1 s | 33× | ✅ prancha |
| 20 | `Estudos/Cursos/Aprovação de Casa/PROJETO FINANCIAMENTO 240,82 m².dwg` | 5.4 MB | 112 MB | amostragem | 112 MB | 39 MB | 11.5 s | 11.4 s | 21× | ✅ prancha |
| 21 | `Estudos/UFRB/Projetos/Projeto AUTO2E/Pav 2/anexo-I-projetos/INST_ELETRICA_TELCOM/INSTALAÇÃO ELÉTRICA/UFRB-CRUZ-ELETRICA1-PAV-AULAS.dwg` | 4.0 MB | 110 MB | amostragem | 110 MB | 43 MB | 10.2 s | 10.1 s | 28× | ✅ prancha |
| 22 | `Estudos/UFRB/Eng. Civil/Barragens/Dimens. Barragem/CET 308 TOPOGRAFIA RIO 2017_2_recover.dwg` | 21.9 MB | 106 MB | amostragem | 106 MB | 0 MB | 4.4 s | 4.3 s | 5× | ✅ prancha |
| 23 | `Estudos/UFRB/Eng. Civil/Saneamento/Projeto/Planta Projeto Impressão Final.dwg_recover.dwg` | 4.6 MB | 102 MB | amostragem | 102 MB | 46 MB | 7.5 s | 7.5 s | 22× | ✅ prancha |
| 24 | `Documentos/Doc Edison/2024_05_20__11_18_29/557581198927/Attach/Media/WhatsApp Documents/Sent/aerhetg.DWG` | 1.9 MB | 92 MB | amostragem | 92 MB | 20 MB | 8.6 s | 8.5 s | 49× | ✅ prancha |
| 25 | `Projetos/Santo Antonio de Jesus/Taluma Cons/VCA/Poligonais em kmz/Desenho2.dwg` | 7.2 MB | 88 MB | amostragem | 88 MB | 23 MB | 4.6 s | 4.5 s | 12× | ✅ prancha |
| 26 | `Projetos/Alagoinhas/Adriana Fisio/02 - IDEALFISIO ADRIANA PARA PCI (2).dwg` | 3.6 MB | 73 MB | amostragem | 73 MB | 18 MB | 10.9 s | 10.8 s | 20× | ✅ prancha + miniatura |
| 27 | `Documentos/Doc Edison/2024_05_20__11_18_29/557581198927/Attach/Media/WhatsApp Documents/Sent/01 Projeto Hidraulico Lote 10-Folha - DT2 - DETALHES ISOMETRICOS-Vista 3D - Isometrico Agua Quente Laje.dwg` | 1.6 MB | 68 MB | amostragem | 68 MB | 0 MB | 6.6 s | 6.6 s | 44× | ✅ prancha |
| 28 | `Documentos/Doc Edison/2024_05_20__11_18_29/557581198927/Attach/Media/WhatsApp Documents/PROJETO PORTAL 02_2022.dwg` | 2.2 MB | 68 MB | amostragem | 68 MB | 0 MB | 26.4 s | 26.2 s | 31× | ✅ prancha |
| 29 | `Estudos/UFRB/Eng. Civil/TCC/anexos sipef/ANEXO II Projetos/PROJETOS COMPLEMENTARES/INCÊNDIO/UFRB-CTC-PCI-PE-004-HE-1ºA-R00.dwg` | 1.8 MB | 59 MB | amostragem | 59 MB | 0 MB | 7.3 s | 7.2 s | 32× | ✅ prancha |
| 30 | `Erica/Edison/03 - PORTAL 01 DRENAGEM E ESGOTO.dwg` | 3.7 MB | 57 MB | amostragem | 57 MB | 15 MB | 8.3 s | 8.2 s | 15× | ✅ prancha + miniatura |
| 31 | `Estudos/UFRB/Eng. Civil/TCC/anexos sipef/ANEXO II Projetos/PROJETOS COMPLEMENTARES/HIDROSANITÁRIO/UFRB-CTC-HID-PE-AP-R00/UFRB-CTC-HID-PE-001-AP-TE-R01.dwg` | 1.5 MB | 56 MB | amostragem | 56 MB | 0 MB | 5.3 s | 5.2 s | 37× | ✅ prancha + miniatura |
| 32 | `Estudos/UFRB/Eng. Civil/TCC/anexos sipef/ANEXO II Projetos/PROJETOS COMPLEMENTARES/HIDROSANITÁRIO/UFRB-CTC-HID-PE-AD-R00/UFRB-CTC-HID-PE-002-AD-1ºA-R00.dwg` | 2.1 MB | 55 MB | amostragem | 55 MB | 0 MB | 8.5 s | 8.5 s | 26× | ✅ prancha + miniatura |
| 33 | `Projetos/Santo Antonio de Jesus/Rycart/Embasa/Estacao Elevatoria/Laboratorio.DWG` | 1.2 MB | 55 MB | amostragem | 55 MB | 0 MB | 6.4 s | 6.4 s | 47× | ✅ prancha |
| 34 | `Estudos/Cursos/Civil 3D/Udemy/Parte 1.dwg` | 2.2 MB | 54 MB | amostragem | 54 MB | 0 MB | 2.9 s | 2.9 s | 25× | ✅ prancha |
| 35 | `Documentos/Doc Edison/2024_05_20__11_18_29/557581198927/Attach/Media/WhatsApp Documents/Sent/Projeto de Rua 02.dwg` | 4.3 MB | 51 MB | amostragem | 51 MB | 0 MB | 1.3 s | 1.2 s | 12× | ✅ prancha |
| 36 | `Estudos/UFRB/Eng. Civil/TCC/anexos sipef/ANEXO II Projetos/PROJETOS COMPLEMENTARES/AR COMPRIMIDO/UFRB-CTC-ARC-PE-001-AC-TE-R00..dwg` | 1.6 MB | 51 MB | amostragem | 51 MB | 0 MB | 7.7 s | 7.7 s | 31× | ✅ prancha + miniatura |
| 37 | `Estudos/UFRB/Projetos/Projeto AUTO2E/Pav 2/anexo-I-projetos/ESTRUTURAL_PL/LAJES/HS-UFBACALMAS_Cob.dwg` | 0.8 MB | 47 MB | amostragem | 30 MB | 47 MB | 10.9 s | 10.9 s | 61× | ✅ prancha + miniatura |
| 38 | `Documentos/Doc Edison/2024_05_20__11_18_29/557581198927/Attach/Media/WhatsApp Documents/As-Built_REAL CONDOMINIO_JANEIRO 2021 (1).DWG` | 1.3 MB | 42 MB | amostragem | 42 MB | 0 MB | 3.2 s | 3.2 s | 33× | ✅ prancha |
| 39 | `Estudos/UFRB/Eng. Civil/Proj. Inst. Elet/Aula Plantao Eng no GDrive/MODELO_RESIDENCIA.dwg` | 0.6 MB | 38 MB | amostragem | 38 MB | 0 MB | 2.5 s | 2.5 s | 63× | ✅ prancha |
| 40 | `Projetos/Santo Antonio de Jesus/Taluma Cons/Portal Residence I/Praças/CAMPO 26_07_21.dwg` | 1.2 MB | 34 MB | amostragem | 34 MB | 0 MB | 4.0 s | 3.9 s | 28× | ✅ prancha + miniatura |
| 41 | `Documentos/Doc Edison/2024_05_20__11_18_29/557581198927/Attach/Media/WhatsApp Documents/Sent/MED_16_03_23_PORTAL 02_.dwg` | 1.3 MB | 34 MB | amostragem | 34 MB | 0 MB | 4.0 s | 4.0 s | 26× | ✅ prancha + miniatura |
| 42 | `Documentos/Doc Edison/2024_05_20__11_18_29/557581198927/Attach/Media/WhatsApp Documents/Sent/10 Projeto do Loteamento atual 04_2022.dwg` | 1.5 MB | 32 MB | amostragem | 32 MB | 0 MB | 4.4 s | 4.4 s | 21× | ✅ prancha |
| 43 | `Documentos/Doc Edison/2024_05_20__11_18_29/557581198927/Attach/Media/WhatsApp Documents/Sent/FILE-5.DWG` | 1.1 MB | 30 MB | amostragem | 30 MB | 0 MB | 2.0 s | 2.0 s | 27× | ✅ prancha + miniatura |
| 44 | `Projetos/Santo Antonio de Jesus/Taluma Cons/Portal Residence I/Praças/TERRAPLANAGEM PRACA DE ESPORTE_.dwg` | 1.1 MB | 27 MB | amostragem | 27 MB | 0 MB | 3.4 s | 3.3 s | 24× | ✅ prancha + miniatura |
| 45 | `Estudos/UFRB/Eng. Civil/Saneamento/Projeto/CONDOMINIONOVITÁ-ARQ-AP-IMP-R03-12-05-14_recover000.dwg` | 1.0 MB | 23 MB | amostragem | 23 MB | 0 MB | 3.4 s | 3.3 s | 22× | ✅ prancha |
| 46 | `Erica/Edison/PORTAL 02 VOLUME GALPAO_.dwg` | 1.0 MB | 22 MB | amostragem | 22 MB | 0 MB | 1.3 s | 1.3 s | 23× | ✅ prancha |
| 47 | `Documentos/Doc Edison/2024_05_20__11_18_29/557581198927/Attach/Media/WhatsApp Documents/Sent/PORTAL 02 GALPAO_.dwg` | 0.8 MB | 21 MB | amostragem | 21 MB | 0 MB | 1.1 s | 1.1 s | 26× | ✅ prancha + miniatura |
| 48 | `Estudos/UFRB/Eng. Civil/TCC/anexos sipef/ANEXO II Projetos/PROJETOS COMPLEMENTARES/ESTRUTURA/ESTRUTURAL RAMPA/FUNDAÇÃO/01_02-DETALHE DAS SAPATAS.dwg` | 0.4 MB | 20 MB | amostragem | 20 MB | 0 MB | 1.4 s | 1.3 s | 51× | ✅ prancha + miniatura |
| 49 | `Documentos/Doc Edison/2024_05_20__11_18_29/557581198927/Attach/Media/WhatsApp Documents/Sent/VIGAS.DWG` | 0.5 MB | 19 MB | amostragem | 19 MB | 0 MB | 2.7 s | 2.7 s | 35× | ✅ prancha |
| 50 | `Documentos/Doc Edison/2024_05_20__11_18_29/557581198927/Attach/Media/WhatsApp Documents/Sent/01 Projeto Hidraulico Lote 10-Folha - PB0 - PLANTAS TERREO-Planta de piso - 0 - Esgoto Terreo.dwg` | 0.5 MB | 18 MB | amostragem | 18 MB | 0 MB | 2.3 s | 2.3 s | 35× | ✅ prancha |
| 51 | `Plantao Engenharia/Banco.dwg` | 1.0 MB | 18 MB | amostragem | 18 MB | 0 MB | 3.6 s | 3.6 s | 17× | ✅ prancha + miniatura |
| 52 | `Estudos/UFRB/Eng. Civil/TCC/anexos sipef/ANEXO II Projetos/PROJETOS COMPLEMENTARES/ESTRUTURA/formas do 1 pavimento.dwg` | 0.3 MB | 17 MB | amostragem | 17 MB | 0 MB | 1.5 s | 1.5 s | 50× | ✅ prancha |
| 53 | `Estudos/UFRB/Projetos/Projeto AUTO2E/Pav 2/anexo-I-projetos/ESTRUTURAL_PL/MC_EST/UFCA200_06_AR.dwg` | 0.4 MB | 17 MB | amostragem | 17 MB | 0 MB | 2.1 s | 2.1 s | 42× | ✅ prancha + miniatura |
| 54 | `Plantao Engenharia/Galpão, Escolas/Escola Estadual.dwg` | 0.7 MB | 17 MB | amostragem | 17 MB | 0 MB | 1.5 s | 1.5 s | 23× | ✅ prancha + miniatura |
| 55 | `Desenho1.dwg` | 1.0 MB | 16 MB | amostragem | 16 MB | 0 MB | 0.4 s | 0.3 s | 17× | ✅ prancha + miniatura |
| 56 | `Erica/Edison/Gilson/1 Andar.dwg` | 0.8 MB | 15 MB | amostragem | 15 MB | 0 MB | 0.4 s | 0.4 s | 18× | ✅ prancha + miniatura |
| 57 | `Documentos/Doc Edison/2024_05_20__11_18_29/557581198927/Attach/Media/WhatsApp Documents/PREF_ROG_08.dwg` | 0.3 MB | 15 MB | amostragem | 15 MB | 0 MB | 1.1 s | 1.1 s | 50× | ✅ prancha |
| 58 | `Projetos/Aratuipe/Passarela/03 ARATUIPE_EMENDA_PASSARELA STEEL/Details/Sheet 008 GA - A0.dwg` | 0.9 MB | 15 MB | amostragem | 15 MB | 0 MB | 2.3 s | 2.3 s | 16× | ✅ prancha |
| 59 | `Estudos/UFRB/Eng. Civil/TCC/anexos sipef/ANEXO II Projetos/PROJETOS COMPLEMENTARES/ESTRUTURA/ESTRUTURAL RAMPA/COBERTURA/01_04-ARMADURAS.dwg` | 0.2 MB | 14 MB | amostragem | 14 MB | 0 MB | 1.2 s | 1.2 s | 63× | ✅ prancha + miniatura |
| 60 | `Estudos/UFRB/Eng. Civil/TCC/anexos sipef/ANEXO II Projetos/PROJETOS COMPLEMENTARES/ESTRUTURA/vigas da cobertura 2.5.dwg` | 0.3 MB | 14 MB | amostragem | 14 MB | 0 MB | 1.4 s | 1.3 s | 53× | ✅ prancha |
| 61 | `Estudos/UFRB/Eng. Civil/TCC/anexos sipef/ANEXO II Projetos/PROJETOS COMPLEMENTARES/ESTRUTURA/vigas do 1 pavimento 4.5.dwg` | 0.2 MB | 14 MB | amostragem | 14 MB | 0 MB | 1.3 s | 1.2 s | 57× | ✅ prancha |
| 62 | `Documentos/Acade 2026/AeData/Proj/JisDemo/025.dwg` | 0.2 MB | 14 MB | amostragem | 14 MB | 0 MB | 1.3 s | 1.2 s | 68× | ✅ prancha |
| 63 | `Estudos/UFRB/Eng. Civil/Proj. Inst. Elet/PLANTA PROJETO ELÉTRICO FINAL.dwg` | 0.3 MB | 13 MB | amostragem | 13 MB | 0 MB | 0.9 s | 0.9 s | 45× | ✅ prancha |
| 64 | `Estudos/UFRB/Projetos/Projeto AUTO2E/Pav 2/anexo-I-projetos/ESTRUTURAL_PL/MC_EST/UFCA100_01_AR.dwg` | 0.3 MB | 13 MB | amostragem | 13 MB | 0 MB | 1.4 s | 1.3 s | 46× | ✅ prancha + miniatura |
| 65 | `Projetos/Santo Antonio de Jesus/Taluma Cons/Portal Residence I/Esgoto/Contencao/Fundaçao Fundo.DWG` | 0.6 MB | 12 MB | amostragem | 12 MB | 0 MB | 0.5 s | 0.5 s | 20× | ✅ prancha |
| 66 | `Documentos/Acade 2026/AeData/Tutorial/Aegs/Schematic terminals/AEGS02.DWG` | 0.2 MB | 12 MB | amostragem | 12 MB | 0 MB | 0.7 s | 0.7 s | 73× | ✅ prancha |
| 67 | `Documentos/Acade 2026/AeData/Tutorial/Aegs/Connector diagrams/AEGS02.DWG` | 0.2 MB | 12 MB | amostragem | 12 MB | 0 MB | 0.7 s | 0.7 s | 73× | ✅ prancha |
| 68 | `Documentos/Acade 2026/AeData/Tutorial/Aegs/Schematic terminals/AEGS09.DWG` | 0.2 MB | 12 MB | amostragem | 12 MB | 0 MB | 1.2 s | 1.1 s | 63× | ✅ prancha |
| 69 | `Documentos/Acade 2026/AeData/Tutorial/Aegs/Connector diagrams/AEGS09.DWG` | 0.2 MB | 12 MB | amostragem | 12 MB | 0 MB | 1.1 s | 1.0 s | 63× | ✅ prancha |
| 70 | `Documentos/Acade 2026/AeData/Tutorial/Aegs/Projects/AEGS09.DWG` | 0.2 MB | 11 MB | amostragem | 11 MB | 0 MB | 1.1 s | 1.1 s | 58× | ✅ prancha |
| 71 | `Documentos/Doc Edison/2024_05_20__11_18_29/557581198927/Attach/Media/WhatsApp Documents/PERFIL MARGINAL PORTAL 02_.dwg` | 0.2 MB | 11 MB | amostragem | 11 MB | 0 MB | 2.0 s | 2.0 s | 53× | ✅ prancha |
| 72 | `Projetos/Aratuipe/Passarela/Imp/3D com Perfis.dwg` | 0.8 MB | 10 MB | amostragem | 10 MB | 0 MB | 0.2 s | 0.2 s | 12× | ✅ prancha |
| 73 | `Documentos/Acade 2026/AeData/Proj/JisDemo/004.dwg` | 0.1 MB | 10 MB | amostragem | 10 MB | 0 MB | 0.5 s | 0.5 s | 73× | ✅ prancha |
| 74 | `Documentos/Acade 2026/AeData/Tutorial/Aegs/Schematic components/AEGS06.DWG` | 0.1 MB | 10 MB | amostragem | 10 MB | 0 MB | 0.6 s | 0.5 s | 90× | ✅ prancha |
| 75 | `Documentos/Acade 2026/AeData/Tutorial/Aegs/Wiring/AEGS06.DWG` | 0.1 MB | 10 MB | amostragem | 10 MB | 0 MB | 0.6 s | 0.6 s | 90× | ✅ prancha |
| 76 | `Documentos/Acade 2026/AeData/Proj/Point2Point/Connector.dwg` | 0.1 MB | 10 MB | amostragem | 10 MB | 0 MB | 0.5 s | 0.5 s | 74× | ✅ prancha |
| 77 | `Documentos/Acade 2026/AeData/Proj/Demo/DEMO06.DWG` | 0.1 MB | 10 MB | amostragem | 10 MB | 0 MB | 0.6 s | 0.6 s | 77× | ✅ prancha |
| 78 | `Documentos/Desenho2_recover.dwg` | 0.9 MB | 10 MB | amostragem | 10 MB | 0 MB | 0.3 s | 0.3 s | 11× | ✅ prancha |
| 79 | `Projetos/Aratuipe/Passarela/05 ARATUIPE_EMENDA_PASSARELA STEEL/Details/Sheet 003 Parts - A1.dwg` | 0.7 MB | 10 MB | amostragem | 10 MB | 0 MB | 0.2 s | 0.2 s | 15× | ✅ prancha |
| 80 | `Estudos/UFRB/Eng. Civil/Proj. Inst. Elet/Projeto Revit/PLANTA PROJETO ELÉTRICO.dwg` | 0.2 MB | 9 MB | amostragem | 9 MB | 0 MB | 0.4 s | 0.4 s | 56× | ✅ prancha + miniatura |
| 81 | `Documentos/Doc Edison/2024_05_20__11_18_29/557581198927/Attach/Media/WhatsApp Documents/Sent/01 Projeto Hidraulico Lote 10-Folha - DT3 - DETALHES-Vista 3D - DET 05.dwg` | 0.4 MB | 8 MB | amostragem | 8 MB | 0 MB | 2.3 s | 2.3 s | 20× | ✅ prancha |
| 82 | `Documentos/C3DMEMO/DWG/CADMEMO.dwg` | 0.4 MB | 8 MB | amostragem | 8 MB | 0 MB | 0.4 s | 0.4 s | 22× | ✅ prancha + miniatura |
| 83 | `Documentos/Doc Edison/2024_05_20__11_18_29/557581198927/Attach/Media/WhatsApp Documents/Vigas_Cobertura_Espaco_Gourmet_EST_Jamylle_Paulo.dwg` | 0.2 MB | 8 MB | amostragem | 8 MB | 0 MB | 0.4 s | 0.4 s | 44× | ✅ prancha + miniatura |
| 84 | `Estudos/UFRB/Eng. Civil/TCC/anexos sipef/ANEXO II Projetos/PROJETOS COMPLEMENTARES/ESTRUTURA/fundações 3.4.dwg` | 0.2 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.8 s | 0.8 s | n/d | ✅ prancha |
| 85 | `Estudos/UFRB/Eng. Civil/TCC/anexos sipef/ANEXO II Projetos/PROJETOS COMPLEMENTARES/ESTRUTURA/pilares do 1 pavimento ao terreo 2.2.dwg` | 0.2 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.7 s | 0.7 s | n/d | ✅ prancha |
| 86 | `Projetos/Aratuipe/Passarela/Imp/ELEVAÇÕES.dwg` | 0.2 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.2 s | 0.2 s | n/d | ✅ prancha |
| 87 | `Estudos/Cursos/Incendio/A$C59B73FC4.DWG` | 0.1 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.8 s | 0.8 s | n/d | ✅ prancha |
| 88 | `Documentos/Acade 2026/AeData/Proj/GbDemo/001.dwg` | 0.1 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.3 s | 0.3 s | n/d | ✅ prancha |
| 89 | `Documentos/Acade 2026/AeData/Proj/IeeeDemo/005.dwg` | 0.1 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.4 s | 0.4 s | n/d | ✅ prancha |
| 90 | `Documentos/Acade 2026/AeData/Proj/IecDemo/006.dwg` | 0.1 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.3 s | 0.2 s | n/d | ✅ prancha |
| 91 | `Projetos/Aratuipe/Passarela/ARATUIPE_EMENDA_PASSARELA STEEL/Details/006.dwg` | 0.2 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.2 s | 0.2 s | n/d | ✅ prancha |
| 92 | `Documentos/Acade 2026/AeData/Proj/Iec60617Demo/007.dwg` | 0.1 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.2 s | 0.2 s | n/d | ✅ prancha |
| 93 | `Documentos/Acade 2026/AeData/Proj/GbDemo/008.dwg` | 0.1 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.2 s | 0.2 s | n/d | ✅ prancha |
| 94 | `Documentos/Acade 2026/AeData/Proj/JisDemo/011.dwg` | 0.1 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.3 s | 0.3 s | n/d | ✅ prancha |
| 95 | `Documentos/Acade 2026/AeData/Proj/IeeeDemo/012.dwg` | 0.1 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.5 s | 0.4 s | n/d | ✅ prancha |
| 96 | `Documentos/Acade 2026/AeData/Proj/IecDemo/013.dwg` | 0.1 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.4 s | 0.4 s | n/d | ✅ prancha |
| 97 | `Documentos/Acade 2026/AeData/Proj/Iec60617Demo/014.dwg` | 0.1 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.5 s | 0.4 s | n/d | ✅ prancha |
| 98 | `Documentos/Acade 2026/AeData/Proj/GbDemo/015.dwg` | 0.1 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.4 s | 0.4 s | n/d | ✅ prancha |
| 99 | `Documentos/Acade 2026/AeData/Proj/JisDemo/018.dwg` | 0.1 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.4 s | 0.4 s | n/d | ✅ prancha |
| 100 | `Documentos/Acade 2026/AeData/Proj/IeeeDemo/019.dwg` | 0.1 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.3 s | 0.3 s | n/d | ✅ prancha |
| 101 | `Anexos/01 Projeto Hidraulico Lote 10-Folha - DT3 - DETALHES.dwg` | 0.0 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.1 s | 0.1 s | n/d | ✅ prancha |
| 102 | `Documentos/Acade 2026/AeData/Proj/IecDemo/020.dwg` | 0.1 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.5 s | 0.5 s | n/d | ✅ prancha |
| 103 | `Documentos/Acade 2026/AeData/Proj/Iec60617Demo/021.dwg` | 0.1 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.5 s | 0.5 s | n/d | ✅ prancha |
| 104 | `Documentos/Acade 2026/AeData/Proj/GbDemo/022.dwg` | 0.1 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.4 s | 0.4 s | n/d | ✅ prancha |
| 105 | `Estudos/UFRB/BCET/Eletricidade/Dos Outros/3Âª Etapa - Interruptores e Tomadas.dwg bruna (1).dwg` | 0.1 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.4 s | 0.4 s | n/d | ✅ prancha |
| 106 | `Documentos/Acade 2026/AeData/Tutorial/Aegs/Symbol Builder/AEGS01.DWG` | 0.1 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.4 s | 0.4 s | n/d | ✅ prancha |
| 107 | `Documentos/Acade 2026/AeData/Tutorial/Aegs/Generating reports/AEGS01.DWG` | 0.1 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.3 s | 0.3 s | n/d | ✅ prancha |
| 108 | `Documentos/Acade 2026/AeData/Tutorial/Aegs/Projects/AEGS02.DWG` | 0.1 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.6 s | 0.6 s | n/d | ✅ prancha |
| 109 | `Documentos/Acade 2026/AeData/Tutorial/Aegs/Panel layout/AEGS03.DWG` | 0.1 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.3 s | 0.3 s | n/d | ✅ prancha |
| 110 | `Documentos/Acade 2026/AeData/Tutorial/Aegs/Title Block/AEGS03.DWG` | 0.1 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.2 s | 0.2 s | n/d | ✅ prancha |
| 111 | `Documentos/Acade 2026/AeData/Tutorial/Aegs/Wire numbers/AEGS03.DWG` | 0.1 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.4 s | 0.4 s | n/d | ✅ prancha |
| 112 | `Documentos/Acade 2026/AeData/Tutorial/Aegs/Block swap/AEGS04.DWG` | 0.1 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.4 s | 0.4 s | n/d | ✅ prancha |
| 113 | `Documentos/Acade 2026/AeData/Tutorial/Aegs/Surf/AEGS05.DWG` | 0.1 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.4 s | 0.4 s | n/d | ✅ prancha |
| 114 | `Documentos/Acade 2026/AeData/Tutorial/Aegs/PLC/AEGS06.DWG` | 0.1 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.5 s | 0.5 s | n/d | ✅ prancha |
| 115 | `Documentos/Acade 2026/AeData/Proj/Aegs/AEGS06.DWG` | 0.1 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.6 s | 0.6 s | n/d | ✅ prancha |
| 116 | `Documentos/Acade 2026/AeData/Tutorial/Aegs/Circuits/AEGS07.DWG` | 0.1 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.5 s | 0.5 s | n/d | ✅ prancha |
| 117 | `Documentos/Acade 2026/AeData/Tutorial/Aegs/Wire layers/AEGS07.DWG` | 0.1 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.5 s | 0.5 s | n/d | ✅ prancha |
| 118 | `Documentos/Acade 2026/AeData/Tutorial/Aegs/AEGS07.DWG` | 0.1 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.5 s | 0.5 s | n/d | ✅ prancha |
| 119 | `Documentos/Acade 2026/AeData/Tutorial/Aegs/Symbol Builder/AEGS08.DWG` | 0.1 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.2 s | 0.2 s | n/d | ✅ prancha |
| 120 | `Documentos/Acade 2026/AeData/Tutorial/Aegs/Generating reports/AEGS08.DWG` | 0.1 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.3 s | 0.3 s | n/d | ✅ prancha |
| 121 | `Documentos/Acade 2026/AeData/Tutorial/Aegs/Panel layout/AEGS10.DWG` | 0.0 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.1 s | 0.1 s | n/d | ✅ prancha |
| 122 | `Documentos/Acade 2026/AeData/Tutorial/Aegs/Title Block/AEGS10.DWG` | 0.0 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.1 s | 0.1 s | n/d | ✅ prancha |
| 123 | `Documentos/Acade 2026/AeData/Tutorial/Aegs/Wire numbers/AEGS10.DWG` | 0.0 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.1 s | 0.1 s | n/d | ✅ prancha |
| 124 | `Documentos/Acade 2026/AeData/Tutorial/Aegs/Block swap/AEGS11.DWG` | 0.0 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.1 s | 0.1 s | n/d | ✅ prancha |
| 125 | `Estudos/UFRB/Eng. Civil/Inst. Hidraulicas/Blocos autocad/banheiras_biblioteca/Bañera051.dwg` | 0.0 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.1 s | 0.1 s | n/d | ✅ prancha + miniatura |
| 126 | `Estudos/UFRB/Eng. Civil/Inst. Hidraulicas/Blocos autocad/banheiras_biblioteca/Bañera058.dwg` | 0.0 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.1 s | 0.1 s | n/d | ✅ prancha + miniatura |
| 127 | `Estudos/UFRB/Eng. Civil/Inst. Hidraulicas/Blocos autocad/banheiras_biblioteca/Bañera065.dwg` | 0.0 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.1 s | 0.1 s | n/d | ✅ prancha + miniatura |
| 128 | `Estudos/UFRB/Eng. Civil/Inst. Hidraulicas/Blocos autocad/banheiras_biblioteca/Bañera072.dwg` | 0.0 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.1 s | 0.1 s | n/d | ✅ prancha + miniatura |
| 129 | `Estudos/UFRB/Eng. Civil/Inst. Hidraulicas/Blocos autocad/banheiras_biblioteca/Bañeras006.dwg` | 0.1 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.1 s | 0.1 s | n/d | ✅ prancha + miniatura |
| 130 | `Estudos/UFRB/Eng. Civil/Inst. Hidraulicas/Blocos autocad/banheiras_biblioteca/Bañeras013.dwg` | 0.0 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.1 s | 0.1 s | n/d | ✅ prancha + miniatura |
| 131 | `Estudos/UFRB/Eng. Civil/Inst. Hidraulicas/Blocos autocad/banheiras_biblioteca/Bañeras020.dwg` | 0.1 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.1 s | 0.1 s | n/d | ✅ prancha + miniatura |
| 132 | `Estudos/UFRB/Eng. Civil/Inst. Hidraulicas/Blocos autocad/banheiras_biblioteca/Bañeras028.dwg` | 0.1 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.1 s | 0.1 s | n/d | ✅ prancha + miniatura |
| 133 | `Estudos/UFRB/Eng. Civil/Inst. Hidraulicas/Blocos autocad/banheiras_biblioteca/Bañeras035.dwg` | 0.0 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.1 s | 0.1 s | n/d | ✅ prancha + miniatura |
| 134 | `Estudos/UFRB/Eng. Civil/Inst. Hidraulicas/Blocos autocad/banheiras_biblioteca/Bañeras042.dwg` | 0.1 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.1 s | 0.1 s | n/d | ✅ prancha + miniatura |
| 135 | `Estudos/UFRB/Eng. Civil/Inst. Hidraulicas/Blocos autocad/banheiras_biblioteca/Bañeras049.dwg` | 0.0 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.1 s | 0.1 s | n/d | ✅ prancha + miniatura |
| 136 | `Estudos/UFRB/Eng. Civil/Inst. Hidraulicas/Blocos autocad/mobilia/camasolteiro.dwg` | 0.0 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.1 s | 0.1 s | n/d | ✅ prancha + miniatura |
| 137 | `Documentos/Acade 2026/AeData/Proj/Aegs/Convert/Convert-03.dwg` | 0.1 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.2 s | 0.2 s | n/d | ✅ prancha |
| 138 | `Documentos/Acade 2026/AeData/Proj/NfpaDemo/DEMO03.DWG` | 0.1 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.3 s | 0.3 s | n/d | ✅ prancha |
| 139 | `Estudos/UFRB/Eng. Civil/Estagio/Estagio QG Engenharia/DESENHO PARA COMPRAS.dwg` | 0.0 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.1 s | 0.1 s | n/d | ✅ prancha |
| 140 | `Estudos/UFRB/BCET/TCC BCET/Drawing1.dwg` | 0.1 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.2 s | 0.2 s | n/d | ✅ prancha |
| 141 | `Projetos/Aratuipe/Passarela/Ligacoes/entrada cima.dwg` | 0.1 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.3 s | 0.3 s | n/d | ✅ prancha |
| 142 | `Estudos/UFRB/Eng. Civil/Inst. Hidraulicas/Modelos/Esgoto_03.dwg` | 0.2 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.8 s | 0.8 s | n/d | ✅ prancha + miniatura |
| 143 | `Documentos/Doc Edison/2024_05_20__11_18_29/557581198927/Attach/Media/WhatsApp Documents/Sent/FILE-1.DWG` | 0.1 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.3 s | 0.3 s | n/d | ✅ prancha |
| 144 | `Estudos/UFRB/Eng. Civil/Inst. Hidraulicas/Blocos autocad/mobilia/freezer.dwg` | 0.0 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.0 s | 0.0 s | n/d | ✅ prancha + miniatura |
| 145 | `Documentos/Acade 2026/AeData/Tutorial/IEC Sample/IEC_02.dwg` | 0.1 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.6 s | 0.6 s | n/d | ✅ prancha |
| 146 | `Documentos/Acade 2026/AeData/Tutorial/IEC Sample/IEC_09.dwg` | 0.1 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.2 s | 0.2 s | n/d | ✅ prancha |
| 147 | `Documentos/Acade 2026/AeData/Tutorial/IEC Sample/IEC_16.dwg` | 0.1 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.2 s | 0.2 s | n/d | ✅ prancha |
| 148 | `Plantao Engenharia/Galpão, Escolas/Neocrotério.dwg` | 0.2 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.4 s | 0.4 s | n/d | ✅ prancha + miniatura |
| 149 | `Documentos/Doc Edison/2024_05_20__11_18_29/557581198927/Attach/Media/WhatsApp Documents/PREF_ROG_01.dwg` | 0.1 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.1 s | 0.1 s | n/d | ✅ prancha |
| 150 | `Estudos/UFRB/BCET/Eletricidade/Plantas/PROJETO DE ELETRICIDADE (PARTE 2) - Edison.dwg` | 0.1 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.2 s | 0.2 s | n/d | ✅ prancha |
| 151 | `Estudos/UFRB/BCET/Eletricidade/Dos Outros/PROJETO DE ELETRICIDADE (PARTE 2) - Marina.dwg` | 0.2 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.2 s | 0.2 s | n/d | ✅ prancha |
| 152 | `Projetos/Aratuipe/Passarela/03 ARATUIPE_EMENDA_PASSARELA STEEL/Details/Cópias de segurança/Sheet 007 GA - A0.dwg` | 0.3 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.2 s | 0.2 s | n/d | ✅ prancha |
| 153 | `Estudos/UFRB/Eng. Civil/Inst. Hidraulicas/Blocos autocad/mobilia/sofa3.dwg` | 0.0 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.1 s | 0.1 s | n/d | ✅ prancha + miniatura |
| 154 | `Projetos/Aratuipe/Passarela/Ligacoes/subida cima cima.dwg` | 0.0 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.1 s | 0.1 s | n/d | ✅ prancha |
| 155 | `Documentos/Acade 2026/AeData/Proj/IeeeDemo/Tabular TermLay/T01.dwg` | 0.1 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.5 s | 0.4 s | n/d | ✅ prancha |
| 156 | `Documentos/Acade 2026/AeData/Proj/IecDemo/Tabular TermLay/T02.dwg` | 0.1 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.5 s | 0.5 s | n/d | ✅ prancha |
| 157 | `Documentos/Acade 2026/AeData/Proj/Iec60617Demo/Tabular TermLay/T03.dwg` | 0.1 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.2 s | 0.2 s | n/d | ✅ prancha |
| 158 | `Documentos/Acade 2026/AeData/Proj/GbDemo/Tabular TermLay/T04.dwg` | 0.1 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.2 s | 0.2 s | n/d | ✅ prancha |
| 159 | `Estudos/UFRB/Eng. Civil/Inst. Hidraulicas/Blocos autocad/tanques1/T560655f.dwg` | 0.0 MB | n/d MB | amostragem | n/d MB | 0 MB | 0.1 s | 0.1 s | n/d | ✅ prancha + miniatura |

## Duas leituras que a tabela sustenta

**1. O tamanho não prevê o custo, e esta é a terceira medição a dizê-lo.** A coluna
`MB/MB` varia por mais de uma ordem de grandeza sobre o mesmo motor e o mesmo
estágio. O arquivo mais caro do acervo não é o mais pesado — é o que declara mais
trabalho (hachura é *declaração*: área ÷ espaçamento do padrão, grandeza que o
tamanho do arquivo não limita). Qualquer knob comercial em MB — e o
`DWG_MB_MOTOR_LIVRE` é um — está medido contra o eixo errado
([planta §12 item 00](../modulos/moduloprancheta.md)).

**2. O caminho da pasta agora sobrevive à importação — e esta tabela é a última
que precisou reconstruí-lo.** A `RevisaoDocumento` passou a guardar
`caminho_origem` (13/08/2026): o lote da R18 sempre leu o caminho relativo para
adivinhar disciplina, código e revisão, e só o descartava em seguida. As linhas
abaixo ainda vêm de um pareamento por **SHA-256** contra a pasta em disco, porque
este acervo foi carregado antes do campo — e é exatamente esse o custo que o campo
elimina: sem ele, *"de qual pasta do escritório veio esta prancha?"* só tem
resposta enquanto alguém ainda tiver a pasta.

**3. Quase metade do acervo não tem pico medido, e isso é da amostragem, não do
acervo.** São 76 dos 159 arquivos cujo subprocesso viveu menos que o intervalo de
50 ms. Eles saem `n/d`, ficam fora da mediana e não viram zero em lugar nenhum —
e o medidor por cgroup (`nucleo/consumo.py`) existe para que a próxima passada não
tenha essa coluna vazia: `memory.peak` não amostra, e conta pai e subprocesso no
mesmo instante. Ligar depende de o deploy delegar um cgroup; enquanto não ligar, a
coluna `Fonte` dirá `amostragem` em todas as linhas.
