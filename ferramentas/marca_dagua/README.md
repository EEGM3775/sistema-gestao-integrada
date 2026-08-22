# Remover marca d'água de PDF

Versão de bancada de uma função que **pertence ao `modulodms`** — a capacidade de PDF da
plataforma ([endereço reservado](../../docs/modulos/modulos-planejados.md)). Aqui ela roda na
máquina, sobre um arquivo em mãos; lá dentro produzirá uma **revisão nova, publicada**, com autor
e rastro. O motor foi escrito para atravessar: funções nomeadas, importáveis por uma task Celery
— só a interface Tkinter fica para trás.

Enquanto isso, não faz parte do backend Django: sem model, rota ou entitlement, e com as
dependências no `requirements.txt` local. O `pymupdf` é **AGPL-3.0** e por isso não entra na
imagem do backend; o porte usará `pikepdf` (MPL-2.0) — ver
[ferramentas/README.md](../README.md#licença--o-pedágio-da-travessia-decidido-antes-de-doer).

Remove a marca editando o fluxo de conteúdo do PDF, **sem rasterizar** a página: o texto
continua selecionável e o arquivo não vira imagem.

## Uso pela interface

```
dist/RemoveMarcaDagua.exe
```

Abre a janela, arraste o PDF (ou arraste sobre o ícone do `.exe`). O programa diagnostica
sozinho e lista os candidatos numa tabela — tipo, detalhe e em quais páginas aparecem. O
primeiro da lista é o suspeito mais provável e já vem selecionado. Clique duplo ou
"Remover selecionado".

O `.exe` é standalone: não precisa de Python nem de venv na máquina.

## Uso pela linha de comando

Sempre comece pelo diagnóstico:

```bash
python remove_marca_dagua.py diagnostico entrada.pdf
```

Depois use o comando correspondente ao que apareceu:

| Diagnóstico mostrou | Comando |
|---|---|
| `TEXTO INCLINADO: 'MARCA'` | `texto entrada.pdf saida.pdf "MARCA"` |
| `XOBJECT: nome=/Fm0` | `xobject entrada.pdf saida.pdf "Fm0"` |
| `Camadas (OCG) ... nome='Watermark'` | `camada entrada.pdf saida.pdf "Watermark"` |
| `ANOTAÇÃO: tipo=Watermark` | `anotacoes entrada.pdf saida.pdf` |
| `IMAGEM: xref=42` | `imagem entrada.pdf saida.pdf 42` |

## Armadilhas

**O modo `texto` apaga o bloco `BT...ET` inteiro.** Se a marca dividir bloco com conteúdo
real, o conteúdo real vai junto. Confira o resultado.

**A string casa byte a byte com o stream, em latin-1.** Se o diagnóstico mostrou
`'R A S C U N H O'` com espaços, é assim que se passa. Prefira um trecho curto e inequívoco
à frase inteira.

**`0 página(s) alterada(s)` significa fonte subsetada.** O texto está em hex/CID no stream e
não existe como ASCII — nenhum alvo de texto vai casar. Nesse caso o alvo real costuma ser o
XObject ou a camada que envolve a marca. Rodar sem casar nada é inofensivo: `_aplicar` só
reescreve o stream quando algo muda.

## Desenvolvimento

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt      # Linux/WSL
.venv\Scripts\pip install -r requirements.txt  # Windows
```

No Linux o Tkinter não vem junto com o Python: `sudo apt install python3-tk`.
Sem `tkinterdnd2` o app não quebra — cai para o botão "Abrir PDF…".

Rebuild do `.exe` (só no Windows):

```powershell
pyinstaller --onefile --windowed --name RemoveMarcaDagua --paths . --noconfirm marca_dagua_gui.py
```

`dist/` e `build/` estão no `.gitignore` da raiz, então o binário de 30 MB não entra em commit.

## Teste

`teste_marca.pdf` tem duas páginas com marca diagonal `CONFIDENCIAL` e conteúdo real, para
validar que a remoção tira a marca e preserva o resto.
