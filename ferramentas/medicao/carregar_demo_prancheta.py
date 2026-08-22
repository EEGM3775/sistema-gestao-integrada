"""Põe pranchas reais do acervo numa obra, para o demo/admin abrir na tela.

**Para que serve:** até aqui a Prancheta foi provada por suíte e por medição de
corpus — nenhum arquivo real do acervo chegou a existir *na tela*, com cartão,
folha, miniatura e fila de decisão. Este carregador fecha isso: escolhe uma obra
(vazia, de preferência), cria um `DocumentoProjeto` por arquivo, sobe a revisão
pela porta única (`funcoesimpexp/entrada.admitir`, R17), publica e enfileira a
conversão.

**Pela porta, e não por `objects.create` direto no `FileField`.** A entrada da
revisão passa por `entrada.admitir` desde a PRA.5a (D75) justamente para que
formato seja reconhecido pelos **bytes** e não pelo nome. Um carregador que
driblasse isso encheria a tela de demo por um caminho que nenhum usuário tem — e
esconderia exatamente a classe de defeito que a porta existe para pegar.

Uso (dentro do container `erp`):

    python manage.py shell < ferramentas/medicao/carregar_demo_prancheta.py

Configurável por ambiente: `DEMO_ACERVO` (pasta), `DEMO_QUANTOS`, `DEMO_OBRA`
(id de uma obra específica), `DEMO_TENANT` (subdomínio/slug).
"""
import os
import pathlib

from django.core.files.base import ContentFile
from django.db import transaction

from moduloprancheta import pipeline
from moduloprancheta.models import DocumentoProjeto, RevisaoDocumento
from nucleo.models import Tenant
from nucleo.tenancy import tenant_context
from obras.models import Obra

ACERVO = pathlib.Path(os.getenv("DEMO_ACERVO", "/acervo"))
QUANTOS = int(os.getenv("DEMO_QUANTOS", "6"))

#: Palavra do caminho → disciplina. O acervo real organiza por pasta, e é dela
#: que a taxonomia da PRA.5b já tira disciplina/código/revisão — aqui a regra é a
#: mesma, reduzida ao que um demo precisa.
POR_PASTA = [
    ("agua", "hidrossanitario"), ("hidraul", "hidrossanitario"),
    ("esgoto", "hidrossanitario"), ("estrutur", "estrutural"),
    ("arq", "arquitetura"), ("eletric", "eletrica"), ("terraplan", "terraplanagem"),
    ("pavim", "pavimentacao"), ("topograf", "topografia"), ("implant", "implantacao"),
]


def disciplina_de(caminho: pathlib.Path) -> str:
    texto = str(caminho).lower()
    for chave, valor in POR_PASTA:
        if chave in texto:
            return valor
    return "outra"


def escolher_tenant() -> Tenant:
    slug = os.getenv("DEMO_TENANT", "")
    if slug:
        return Tenant.objects.get(slug=slug)
    # O tenant do demo é o que tem usuário `demo`; sem ele, o primeiro.
    from nucleo.models import Usuario
    usuario = Usuario.objects.filter(username="demo").select_related("tenant").first()
    return usuario.tenant if usuario and usuario.tenant else Tenant.objects.first()


def escolher_obra(tenant: Tenant) -> Obra:
    """Uma obra **vazia**, de preferência — para a demo não se misturar ao que já existe.

    `DEMO_OBRA_NOVA=<nome>` cria uma obra própria para a carga, que é o que se
    quer quando os arquivos são um conjunto com tese (os difíceis, por exemplo):
    misturá-los a uma obra existente esconderia justamente o que se foi ver.
    """
    nome_novo = os.getenv("DEMO_OBRA_NOVA", "")
    if nome_novo:
        obra, criada = Obra.objects.get_or_create(
            tenant=tenant, nome_obra=nome_novo,
            defaults={
                "endereco": "Acervo da construtora",
                "descricao": "Carga de acervo real para teste de usuário.",
            },
        )
        print(f"obra {'criada' if criada else 'reaproveitada'}: {nome_novo}")
        return obra
    if os.getenv("DEMO_OBRA"):
        return Obra.objects.get(pk=int(os.getenv("DEMO_OBRA")))
    com_projeto = set(
        DocumentoProjeto.objects.values_list("obra_id", flat=True).distinct()
    )
    vazias = [o for o in Obra.objects.all() if o.pk not in com_projeto]
    if vazias:
        return vazias[0]
    return Obra.objects.first()


def arquivos() -> list[pathlib.Path]:
    """Os DWGs a carregar — uma lista declarada, ou o acervo do menor ao maior.

    **`DEMO_LISTA` aponta um arquivo de caminhos relativos ao acervo**, e existe
    para carregar um conjunto *escolhido*: os que deram trabalho. Uma vitrine
    montada só com o que sempre coube prova pouco — quem tem de abrir na tela é
    a prancha que antes não abria.

    Sem lista, o padrão antigo: do menor para o maior. **Do menor para o maior
    era decisão, não conveniência** — os pesados estouravam o orçamento de
    conversão (§4.6) e apareceriam na tela como erro. Desde a hachura nativa
    (12/08/2026) isso deixou de valer para a prancha de disciplina, que era a
    maior parte dos casos ruins; segue valendo para o executivo grande.
    """
    lista = os.getenv("DEMO_LISTA", "")
    if lista:
        escolhidos = []
        for linha in pathlib.Path(lista).read_text(encoding="utf-8").splitlines():
            relativo = linha.strip()
            if not relativo:
                continue
            caminho = ACERVO / relativo
            if caminho.is_file():
                escolhidos.append(caminho)
            else:
                # Sem silêncio: uma lista que perdeu arquivo carrega outra coisa.
                print(f"  ! fora do acervo, pulado: {relativo}")
        return escolhidos

    achados = [p for p in ACERVO.rglob("*") if p.suffix.lower() == ".dwg"]
    achados = [p for p in achados if p.stat().st_size > 0]
    achados.sort(key=lambda p: p.stat().st_size)
    # Pula os minúsculos: abaixo de ~200 KB o acervo tem esboço e arquivo de
    # recuperação, que não mostram nada na tela.
    return [p for p in achados if p.stat().st_size > 200_000][:QUANTOS]


tenant = escolher_tenant()
print(f"tenant: {tenant} (id={tenant.pk})")

with tenant_context(tenant.pk):
    obra = escolher_obra(tenant)
    print(f"obra:   {obra} (id={obra.pk})")
    lista = arquivos()
    print(f"arquivos: {len(lista)}\n")

    for ordem, caminho in enumerate(lista, 1):
        tamanho = caminho.stat().st_size
        disciplina = disciplina_de(caminho)
        codigo = f"DEMO-{ordem:02d}"
        try:
            with transaction.atomic():
                documento, _ = DocumentoProjeto.objects.get_or_create(
                    tenant=tenant, obra=obra, codigo=codigo,
                    defaults={
                        "titulo": caminho.stem[:180],
                        "disciplina": disciplina,
                        "projetista": "Acervo da construtora",
                        "descricao": f"Carregado do acervo para demonstração: {caminho.name}",
                    },
                )
                revisao = RevisaoDocumento(
                    tenant=tenant, documento=documento, revisao="R00",
                    nome_original=caminho.name, formato="dwg",
                    # Relativo ao acervo, como o lote da R18 grava: é o que
                    # torna a tabela de custo por arquivo legível sem
                    # reconstruir nada por SHA-256 contra a pasta de origem.
                    caminho_origem=str(caminho.relative_to(ACERVO))[:1024],
                    tamanho_bytes=tamanho,
                    situacao=RevisaoDocumento.Situacao.VIGENTE,
                )
                revisao.arquivo.save(
                    caminho.name, ContentFile(caminho.read_bytes()), save=False,
                )
                revisao.save()
            # **O `agendar` vai numa transação própria, e não num `on_commit`.**
            # Na API ele vive no `on_commit` porque lá o tenant da conexão é
            # posto pelo middleware, por requisição; aqui quem o põe é o
            # `tenant_context`, que usa `SET LOCAL` — e `LOCAL` morre junto com a
            # transação. O callback então rodava com a variável já limpa e o
            # INSERT da derivada batia na RLS ("new row violates row-level
            # security policy"), que é a política funcionando, não um defeito.
            with tenant_context(tenant.pk), transaction.atomic():
                pipeline.agendar(revisao)
            print(f"  {ordem}. {caminho.name[:52]:52} {tamanho/1048576:6.1f} MB  "
                  f"{disciplina:16} doc={documento.pk} rev={revisao.pk}")
        except Exception as erro:  # noqa: BLE001 — um arquivo ruim não derruba a carga
            print(f"  {ordem}. {caminho.name[:52]:52} FALHOU: {type(erro).__name__}: {erro}")

    print(f"\nPronto. Abra /app/prancheta e escolha a obra '{obra}'.")
    print("As conversões rodam no worker-conversao; o cartão sai de LENDO para PRONTO sozinho.")
