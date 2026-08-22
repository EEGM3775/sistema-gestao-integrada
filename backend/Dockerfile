# ---------------------------------------------------------------------------
# Estágio 1 — GNU LibreDWG (motor livre de DWG da Prancheta, PRA.1)
# ---------------------------------------------------------------------------
# **Por que compilar em vez de instalar:** o LibreDWG NÃO é empacotado pelo
# Debian — não há `libredwg` em bookworm, trixie nem sid. Como esta imagem é
# `python:3.12-slim` (Debian), não existe `apt-get install` que resolva.
#
# **Por que um COMMIT do git e não mais a tarball do GNU** *(09/08/2026, D43)*.
# A escolha anterior era a tarball assinada de ftp.gnu.org, por ser ponto fixo e
# arquivado. O que mudou não foi a preferência, foi a medida: o **0.13.3 é o
# release mais novo publicado** (conferido no ftp — não há 0.13.4, e ele é de
# 2023), e 12 arquivos do corpus paravam no *decodificador* dele. Medidos os
# mesmos 19 alvos pelo pipeline inteiro, nos dois binários:
#
#   0.13.3      →  7 convertidos, 12 em `dxf_intermediario_ilegivel` (fila NOSSA)
#   0.14.8566   → 19 convertidos, 0 falhas, 0 regressões
#
# Não é só legibilidade: `com_blocos_ausentes` cai de 3 para 0 e `multifolha`
# sobe de 2 para 4 — arquivo que vinha pela metade passa a vir inteiro. E o bug
# que o nosso `remendar_continuacoes` remenda (texto cortado em 255 bytes sem o
# código de continuação) está corrigido a montante: `convertido_apos_reparo`
# some do relatório. O remendo fica como rede, não como muleta.
#
# **A GPLv3 continua cumprida, e o cumprimento mudou de forma junto.** A tarball
# era "arquivado por terceiro"; um commit não é — histórico pode ser reescrito.
# Por isso o estágio gera o **fonte correspondente** do próprio commit
# (`git archive`) e a imagem final o carrega ao lado do COPYING: a oferta do §6
# passa a ser satisfeita pela própria imagem, sem depender de o GitHub
# preservar nada. Ver THIRD-PARTY-LICENSES.md.
#
# **Licença:** GPLv3. O binário é chamado como processo separado pelo backend
# (`moduloprancheta/motores/dwg.py`), então o nosso código segue proprietário —
# mas a imagem passa a redistribuir GPL, e por isso o COPYING viaja junto.
#
# **Custo:** este estágio acrescenta minutos ao build. Removê-lo NÃO quebra o
# sistema: o adaptador não supõe que o binário exista e declara
# `motor_indisponivel` em `GET /api/prancheta/status/`. O que se perde é DWG.
FROM python:3.12-slim AS libredwg

# O commit é o número da versão aqui: `dwg2dxf --version` diz `0.14.8566`, que é
# o que o `medir_cobertura_dwg` grava no parcial. Subir este hash é mudança
# deliberada — e exige remedir, porque é o motor que produz a taxa de cobertura.
ARG LIBREDWG_COMMIT=a8ce24891c1a82cd51a8d0f3f97095a2a5d8aa31
ARG LIBREDWG_GIT=https://github.com/LibreDWG/libredwg.git
# `autoconf/automake/libtool/texinfo` são o preço do git: a tarball do GNU vinha
# com o `configure` pronto, o repositório não (daí o `autogen.sh`).
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential ca-certificates git xz-utils \
        autoconf automake libtool pkg-config texinfo gperf perl \
        libpcre2-dev \
    && rm -rf /var/lib/apt/lists/*
# `--filter=blob:none` traz o histórico sem os blobs: o `git-version-gen` do
# projeto precisa das tags para compor `0.14.8566` (com `--depth 1` a versão sai
# genérica e o parcial da medição deixa de identificar o motor), e o clone
# continua rápido porque só o commit pedido materializa arquivo.
RUN git clone --filter=blob:none "$LIBREDWG_GIT" /tmp/libredwg \
    && git -C /tmp/libredwg checkout --detach "$LIBREDWG_COMMIT"
WORKDIR /tmp/libredwg
# O fonte correspondente da GPLv3 §6, gerado do próprio commit que virou binário.
# **Custo medido: 25 MB** na imagem final (1,57 → 1,61 GB), quase tudo dado de
# teste do próprio LibreDWG. `xz -9` cortaria isso para perto da metade ao preço
# de ~1 min de build; fica anotado como opção, não como pendência — 1,5% da
# imagem é preço barato pela oferta de fonte não depender de terceiro.
RUN mkdir -p /opt/libredwg/share/licenses \
    && git archive --format=tar --prefix="libredwg-${LIBREDWG_COMMIT}/" HEAD \
       | gzip -6 > "/opt/libredwg/share/licenses/fonte-libredwg-${LIBREDWG_COMMIT}.tar.gz" \
    && git log -1 --format='%H%n%ad%n%s' --date=iso > /opt/libredwg/share/licenses/COMMIT
# `--disable-bindings` corta o SWIG (Python/Perl), que não usamos e que puxaria
# meia toolchain. `--disable-shared` deixa o `dwg2dxf` autocontido, para o
# estágio final receber um arquivo só em vez de um binário + .so a rastrear.
#
# `--disable-werror` NÃO é conveniência: sem ele o build QUEBRA. O
# `python:3.12-slim` já veio para o GCC 14, que estreou o
# `-Walloc-size`; ele acusa ~40 `malloc()` de tamanho menor que o struct em
# `src/encode.c`, e o `-Werror` do projeto os promove a erro. Dois motivos para
# desligar em vez de remendar: (a) o padrão é intencional lá em cima (o struct
# tem cauda de tamanho variável) e (b) **encode é o ESCRITOR de DWG** — a metade
# que a própria documentação do LibreDWG chama de fraca e que o nosso caminho
# não toca, porque `dwg2dxf` decodifica. Nenhum aviso caiu no decodificador.
# Manter o `-Werror` aqui seria deixar o build do backend refém do aviso novo do
# GCC seguinte, num código de terceiro que não vamos consertar.
#
# `install-strip` em vez de `install`: o binário estático sai com 66 MB de
# símbolos de debug que só pesariam na imagem final.
#
# `JOBS` tem padrão 4 e não `nproc` de propósito: este build roda na estação de
# trabalho do dono, e `nproc` num 12-core toma a máquina inteira por minutos.
# Quem tiver servidor passa `--build-arg JOBS=$(nproc)`.
ARG JOBS=4
RUN sh autogen.sh \
    && ./configure --prefix=/opt/libredwg --disable-shared --enable-static --disable-bindings \
        --disable-werror \
    && make -j"$JOBS" \
    && make install-strip \
    && mkdir -p /opt/libredwg/share/licenses \
    && cp COPYING /opt/libredwg/share/licenses/


# ---------------------------------------------------------------------------
# Estágio 2 — a imagem do backend
# ---------------------------------------------------------------------------
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependências de sistema: psycopg2/build + WeasyPrint (pango/cairo) para PDFs
# + GEOS/GDAL/PROJ do GeoDjango (MAP.0). As três bibliotecas geo são carregadas
# por ctypes em tempo de import de `django.contrib.gis`: sem elas o processo NÃO
# sobe (ImproperlyConfigured), não é degradação. `binutils` entra porque é o que
# dá `objdump` ao `ctypes.util.find_library` — é a receita da doc do Django para
# Debian, e sem ele a busca pela libgdal falha mesmo com o pacote instalado.
#
# `gdal-bin` sozinho puxa libgdal, libgeos e libproj como dependência. Fixar os
# nomes versionados (libgdal32, libproj25) quebra a cada troca de base do
# `python:3.12-slim` — o Debian renumera essas libs a cada release, e foi
# exatamente o que aconteceu na trixie.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        libpango-1.0-0 libpangocairo-1.0-0 libpangoft2-1.0-0 \
        libcairo2 libgdk-pixbuf-2.0-0 libffi8 shared-mime-info \
        fonts-liberation \
        binutils gdal-bin \
    && rm -rf /var/lib/apt/lists/*

# Motor livre de DWG + a licença que a GPLv3 manda distribuir junto (estágio 1).
# O caminho fica no PATH, então `shutil.which("dwg2dxf")` acha; `LIBREDWG_DWG2DXF`
# existe como escape se algum ambiente o instalar em outro lugar.
COPY --from=libredwg /opt/libredwg/bin/dwg2dxf /usr/local/bin/dwg2dxf
# `dwgbmp` extrai o thumbnail que o próprio CAD gravou no DWG (planta §4.4). É a
# ÚNICA figura do acervo que não é redesenho nosso, e vale mais exatamente onde o
# redesenho falha — o cartão que hoje fica vazio. Ficou fora do PRA.1 por
# esquecimento (D49); são +13 MB na imagem, do mesmo build stage já pago.
COPY --from=libredwg /opt/libredwg/bin/dwgbmp /usr/local/bin/dwgbmp
# `dwg2SVG` nasceu como INSTRUMENTO DE MEDIÇÃO e desde 10/08/2026 é também o
# ÚLTIMO DEGRAU da escada de conversão (`ECONOMIA_SVG_DIRETO`). Como instrumento,
# responde à pergunta do D43 pelo `medir_cobertura_dwg --resgate`; como degrau,
# desenha quando o nosso caminho (dwg2dxf → ezdxf) estourou o orçamento e a
# alternativa seria não entregar prancha nenhuma. São +13 MB do estágio já pago.
#
# **A ressalva de sempre continua valendo, e é por isso que ele é o ÚLTIMO:** o
# SVG dele não passa pelo `Recorder`, e é o `Recorder` que produz a folha — logo,
# sem separação por desenho (PRA.1c), sem âncora de marcação e sem escala. Como
# degrau final ele só é alcançado onde hoje não há prancha, então nada do que já
# converte muda de aparência. **Promovê-lo a caminho PRINCIPAL** — que é o que
# corta 4× a memória do caso comum (225 MB contra 945 MB, medido na §4.1 da
# planta) — **exige refazer folha, âncora e escala**, e continua sendo decisão de
# fatia e não consequência de uma linha de COPY.
COPY --from=libredwg /opt/libredwg/bin/dwg2SVG /usr/local/bin/dwg2SVG
COPY --from=libredwg /opt/libredwg/share/licenses/COPYING /usr/share/licenses/libredwg/COPYING
# O **fonte correspondente** (GPLv3 §6) e a identificação do commit viajam dentro
# da imagem. É o que torna a oferta cumprível por quem tem a imagem, sem
# depender do GitHub — a garantia que a tarball do ftp.gnu.org dava de graça e um
# commit não dá.
COPY --from=libredwg /opt/libredwg/share/licenses/fonte-libredwg-*.tar.gz /usr/share/licenses/libredwg/
COPY --from=libredwg /opt/libredwg/share/licenses/COMMIT /usr/share/licenses/libredwg/COMMIT

# ATENÇÃO: o contexto de build é a RAIZ do repositório (ver deploy/compose/base.yml),
# não backend/. É o que permite copiar o pacote compartilhado `funcoesemail/`.
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .
# Pacote compartilhado com a IAM: textos e transporte de e-mail (funcoesemail/README.md).
COPY funcoesemail/ ./funcoesemail/
# Idem: planos, quotas e preços (payment/README.md). O backend passou a precisar
# deles no D24, para servir o medidor de quota e a vitrine de upgrade a partir da
# MESMA tabela que a IAM usa para emitir os tetos.
COPY payment/ ./payment/
# Aviso de licenças redistribuídas — a metade documental da obrigação GPLv3 do
# LibreDWG. A outra metade (o COPYING) já veio do estágio 1.
COPY THIRD-PARTY-LICENSES.md /usr/share/licenses/THIRD-PARTY-LICENSES.md

EXPOSE 8000

# Aplica migrações e sobe via gunicorn. Em produção, rode `migrate` num passo
# separado (job) em vez de no entrypoint.
CMD ["sh", "-c", "python manage.py migrate --noinput && gunicorn config.wsgi:application --bind 0.0.0.0:8000"]
