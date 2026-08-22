# Licenças de terceiros redistribuídas nas imagens do SGI

> Este documento existe para uma obrigação **legal**, não organizacional: algumas
> imagens do sistema **redistribuem** software de terceiros sob licenças que
> exigem aviso e, num caso, oferta de código-fonte. Fechar essa obrigação é
> trabalho de quem adiciona o componente, na mesma fatia — não de quem descobre o
> problema depois.
>
> **Regra:** componente que a imagem apenas *usa via rede* (API da NFE.io, Asaas,
> Nominatim) não entra aqui. Entra o que é **copiado para dentro da imagem** e
> distribuído junto dela.

## GNU LibreDWG — GPLv3 · imagem `sgi-erp` (backend)

**O que é.** O binário `dwg2dxf`, usado pelo módulo Prancheta para converter DWG
em DXF antes de desenhá-lo ([`backend/moduloprancheta/motores/dwg.py`](backend/moduloprancheta/motores/dwg.py)).
É a metade livre do "nó do DWG" descrito em
[docs/modulos/moduloprancheta.md §4.1](docs/modulos/moduloprancheta.md).

**Licença.** GNU General Public License v3 ou posterior.

**Por que o nosso código continua proprietário.** O `dwg2dxf` é invocado como
**processo separado** (`subprocess.run`), com comunicação por arquivo. Não há
linkagem, nem import, nem embutimento: o SGI e o LibreDWG são dois programas que
trocam arquivos, e a GPL não atravessa essa fronteira. Trocar a chamada por um
binding em processo (`ctypes`, extensão compilada, `libredwg` como biblioteca)
**mudaria a análise** — é uma decisão de licenciamento disfarçada de refatoração,
e por isso está registrada no topo do adaptador.

> **Pergunta do dono (16/08/2026): "isso pode colocar todo o meu código público?"**
> **Não.** Ninguém adquire direito ao código do SGI por causa do LibreDWG. A GPL
> alcança *obra derivada*, e subprocesso trocando arquivo não é derivada — o que
> se distribui junto do binário é o **fonte do LibreDWG**, que já viaja na imagem
> (§6(a), na tabela abaixo), nunca o nosso.
>
> Fica registrado aqui porque a pergunta vai voltar, e porque a resposta tem
> **uma condição**: ela vale enquanto a chamada for por processo. O dia em que
> alguém "otimizar" o adaptador para `ctypes` — trocando o custo de um `fork`
> pela conveniência de chamar a função direto — essa conveniência custa o
> licenciamento do produto. Não há aviso automático para isso hoje; é revisão
> humana no `motores/dwg.py`.

**O que a distribuição exige, e como cumprimos:**

| Obrigação (GPLv3 §4–6) | Como é cumprida |
|---|---|
| Aviso de licença junto do binário distribuído | Este documento + cópia da GPLv3 em `/usr/share/licenses/libredwg/` na imagem |
| Manter os avisos de copyright originais | Preservados pelo `make install` do build stage |
| Oferta de código-fonte correspondente | **A imagem carrega o fonte, não uma promessa de fonte** (§6(a), 09/08/2026): o build stage compila de um **commit fixado** (`LIBREDWG_COMMIT` no [Dockerfile](backend/Dockerfile)) e gera dele um `git archive`, que a imagem final guarda em `/usr/share/licenses/libredwg/fonte-libredwg-<commit>.tar.gz`, ao lado de um `COMMIT` com hash, data e assunto. Pedidos por outro canal: o mesmo contato do produto |

> **Por que o fonte passou a viajar dentro da imagem.** Até 09/08/2026 o binário
> vinha da tarball assinada de ftp.gnu.org, e a oferta de fonte se resolvia
> apontando para um arquivo público que o GNU mantém. O [D43](docs/historico-correcoes.md)
> trocou a tarball 0.13.3 por um commit do master — a única versão que decodifica
> os DWGs que paravam o motor —, e commit **não é ponto arquivado**: histórico
> pode ser reescrito e repositório pode sair do ar. Guardar o `git archive` junto
> do binário devolve a garantia que a tarball dava de graça, e custa alguns MB.

**Nota operacional que motivou o build stage.** O LibreDWG **não é empacotado
pelo Debian** — não há pacote `libredwg` em bookworm, trixie nem sid (conferido
no `packages.debian.org`). Como a imagem do backend é `python:3.12-slim`
(Debian), não existe `apt-get install` que resolva, e o binário entra compilado
de fonte num estágio separado do `Dockerfile`. Consequência de engenharia
registrada no adaptador: ele **não supõe** que o binário exista; a ausência é
`motor_indisponivel` (problema nosso, resolvido por deploy) e nunca
`motor_insuficiente` (limite de plano, resolvido por compra).

## Componentes sem obrigação de redistribuição

Listados para que a ausência seja deliberada, e não esquecimento:

| Componente | Licença | Por que não exige nada além do aviso |
|---|---|---|
| `ezdxf` | MIT | Permissiva; aviso mantido no pacote instalado |
| `IfcOpenShell` | LGPL-3.0 | Usado como biblioteca Python **não modificada**; a LGPL exige poder substituí-la, o que `pip install` já permite |
| `pypdfium2` / PDFium | Apache-2.0 / BSD-3 | Permissivas |
| Pillow, WeasyPrint, GDAL/GEOS/PROJ | MIT / BSD / MIT | Permissivas |
| **xeokit** | AGPLv3 | **Não usado — deliberadamente.** É o viewer BIM open-source mais citado e é incompatível com SaaS proprietário sem licença comercial. Registrado aqui para ninguém adotá-lo por engano ([planta §4](docs/modulos/moduloprancheta.md)) |
| **PyMuPDF** (`fitz`) | AGPLv3 | **Fora das imagens — deliberadamente.** É a biblioteca de PDF mais conveniente do ecossistema Python e resolve marca d'água, carimbo e página em poucas linhas; entra em `backend/` e o produto inteiro passa a servir AGPL pela rede (§13). Vive só na bancada ([ferramentas/marca_dagua/](ferramentas/README.md)), que não distribui nem serve nada. A capacidade de PDF do produto se apoiará no **`pikepdf`** (MPL-2.0 / QPDF Apache-2.0) — decisão registrada em [modulos-planejados.md](docs/modulos/modulos-planejados.md) |
