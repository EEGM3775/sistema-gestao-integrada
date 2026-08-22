# backend/moduloprancheta/interop.py
"""A ponte entre o BCF e o banco — o que [`bcf.py`](bcf.py) de propósito não faz.

O parser não conhece ORM (é o que permite testá-lo sem banco, e o que impede que
uma mudança de modelo quebre a leitura de um formato que não é nosso). Este
módulo é o outro lado: pega o que ele leu e decide o que vira linha.

**A regra que governa tudo aqui é o GUID.** Marcação, comentário e ponto de vista
carregam o identificador do BCF, e é por ele que a ida e volta funciona: exportar
um tópico, respondê-lo no Solibri e reimportar o arquivo reencontra a MESMA linha
em vez de criar uma segunda. Sem isso, cada ciclo com o escritório duplicaria a
caixa de entrada do canteiro — que é o defeito que faz equipe abandonar
integração BCF na segunda semana.

**O que a importação sobrescreve, e o que ela não toca.** Sobrescreve o que é do
padrão e mudou lá fora (situação, prioridade, prazo, responsável, título,
descrição) — porque o arquivo do projetista é notícia mais nova sobre o tópico
dele. Não toca em `ancora` nem em `revisao`: a coordenada na folha e a prancha a
que a marcação pertence são nossas, o BCF não as carrega, e reescrevê-las com o
default do formato apagaria informação que só existe aqui.
"""
from __future__ import annotations

import io
import logging

from django.core.files.base import ContentFile
from django.db import transaction

from . import bcf
from .models import ComentarioMarcacao, Marcacao, PontoDeVista

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exportação
# ---------------------------------------------------------------------------
def exportar(marcacoes) -> bytes:
    """Monta o `.bcfzip` das marcações informadas.

    Recebe um queryset já escopado pelo chamador — este módulo não filtra por
    tenant, porque quem sabe o escopo é a view (e a RLS por baixo). Assumir aqui
    que "todas as marcações" é seguro seria o começo de um vazamento.
    """
    topicos: list[bcf.TopicoBcf] = []
    snapshots: dict[str, bytes] = {}

    for marcacao in marcacoes:
        topico = bcf.TopicoBcf(
            guid=str(marcacao.guid),
            titulo=marcacao.titulo,
            descricao=marcacao.descricao,
            tipo=marcacao.tipo,
            situacao=marcacao.situacao,
            prioridade=marcacao.prioridade,
            rotulos=[str(r) for r in (marcacao.rotulos or [])],
            prazo=marcacao.prazo,
            # `CreationAuthor` é texto no padrão: quem tem login vai pelo
            # username, quem veio de fora mantém o nome que veio — trocar por
            # quem apenas subiu o arquivo reescreveria a autoria.
            autor=(marcacao.criado_por.username if marcacao.criado_por_id else marcacao.autor_nome),
            data_criacao=marcacao.criado_em,
            responsavel_email=_email_do_responsavel(marcacao),
        )

        for comentario in marcacao.comentarios.all():
            topico.comentarios.append(bcf.ComentarioBcf(
                guid=str(comentario.guid),
                texto=comentario.texto,
                autor=(comentario.autor.username if comentario.autor_id else comentario.autor_nome),
                data=comentario.criado_em,
                ponto_de_vista_guid=(
                    str(comentario.ponto_de_vista.guid) if comentario.ponto_de_vista_id else ""
                ),
            ))

        for ponto in marcacao.pontos_de_vista.all():
            topico.pontos_de_vista.append(bcf.PontoDeVistaBcf(
                guid=str(ponto.guid), camera=ponto.camera or {},
            ))
            if ponto.snapshot:
                try:
                    with ponto.snapshot.open("rb") as arquivo:
                        snapshots[str(ponto.guid)] = arquivo.read()
                except (FileNotFoundError, OSError):
                    # Snapshot fora do armazenamento (volume trocado, expurgo)
                    # não pode derrubar a exportação inteira: o tópico vale sem a
                    # imagem, e é o que o projetista precisa ler.
                    logger.warning(
                        "prancheta_bcf_snapshot_ausente",
                        extra={"ponto_de_vista": ponto.pk},
                    )
        topicos.append(topico)

    return bcf.escrever(topicos, snapshots=snapshots)


def _email_do_responsavel(marcacao: Marcacao) -> str:
    """`AssignedTo` do BCF é e-mail, e o do usuário com login vale mais que o
    texto solto — é ele que a ferramenta do escritório usa para notificar."""
    if marcacao.responsavel_id and marcacao.responsavel.email:
        return marcacao.responsavel.email
    return marcacao.responsavel_email


# ---------------------------------------------------------------------------
# Importação
# ---------------------------------------------------------------------------
def _imagem_valida(dados: bytes) -> bool:
    """Confere que o snapshot é imagem de verdade antes de virar arquivo.

    O `ImageField` só valida no `full_clean()`, que o `.save()` direto não
    chama. Sem esta checagem, qualquer conteúdo dentro do zip viraria um `.png`
    no nosso armazenamento — servido depois com `nosniff` e `attachment`, então
    não executável, mas ainda assim bytes arbitrários de origem externa gravados
    como se fossem imagem.
    """
    try:
        from PIL import Image

        Image.open(io.BytesIO(dados)).verify()
        return True
    except Exception:
        return False


@transaction.atomic
def importar(conteudo: bytes, *, revisao, usuario, tenant) -> dict:
    """Lê o BCF e concilia com o acervo. Atômico: entra inteiro ou não entra.

    Levanta `bcf.BcfInvalido` (arquivo ilegível/hostil) — a view a traduz em 400
    com a mensagem, que é escrita para o usuário e não para o log.

    Devolve o resumo do que aconteceu, e ele é o produto tanto quanto as linhas:
    "12 novas, 3 atualizadas" é o que diz ao projetista se o arquivo que ele
    mandou era o que ele achava que era.
    """
    topicos = bcf.ler(conteudo)

    resumo = {"criadas": 0, "atualizadas": 0, "comentarios": 0, "pontos_de_vista": 0}
    for topico in topicos:
        marcacao, criada = _conciliar_marcacao(topico, revisao=revisao, usuario=usuario, tenant=tenant)
        resumo["criadas" if criada else "atualizadas"] += 1
        resumo["pontos_de_vista"] += _conciliar_pontos(topico, marcacao, tenant=tenant)
        resumo["comentarios"] += _conciliar_comentarios(topico, marcacao, tenant=tenant)

    resumo["total"] = len(topicos)
    return resumo


def _conciliar_marcacao(topico: bcf.TopicoBcf, *, revisao, usuario, tenant) -> tuple[Marcacao, bool]:
    existente = Marcacao.objects.filter(tenant=tenant, guid=topico.guid).first()

    campos = {
        "titulo": topico.titulo or "(sem título)",
        "descricao": topico.descricao,
        "tipo": _valor_conhecido(topico.tipo, Marcacao.Tipo, Marcacao.Tipo.PROBLEMA),
        "situacao": _valor_conhecido(topico.situacao, Marcacao.Situacao, Marcacao.Situacao.ABERTA),
        "prioridade": _valor_conhecido(
            topico.prioridade, Marcacao.Prioridade, Marcacao.Prioridade.NORMAL
        ),
        "rotulos": topico.rotulos,
        "prazo": topico.prazo,
        "responsavel_email": topico.responsavel_email,
        "responsavel": _usuario_do_email(topico.responsavel_email, tenant),
        "autor_nome": topico.autor,
    }

    if existente:
        # `revisao` e `ancora` ficam de fora (ver o cabeçalho): são nossas, o BCF
        # não as carrega, e sobrescrevê-las com o default apagaria o que só
        # existe aqui.
        for campo, valor in campos.items():
            setattr(existente, campo, valor)
        existente.save(update_fields=[*campos.keys(), "atualizado_em"])
        return existente, False

    marcacao = Marcacao.objects.create(
        tenant=tenant,
        revisao=revisao,
        guid=topico.guid,
        origem=Marcacao.Origem.BCF,
        # A data do BCF é quando o problema foi apontado, não quando o arquivo
        # chegou aqui — a lição do L7 (ver `Marcacao.criado_em`).
        criado_em=topico.data_criacao or _agora(),
        # `criado_por` fica nulo de propósito: quem subiu o arquivo NÃO é quem
        # escreveu a marcação. A autoria real está em `autor_nome`.
        criado_por=None,
        **campos,
    )
    return marcacao, True


def _conciliar_pontos(topico: bcf.TopicoBcf, marcacao: Marcacao, *, tenant) -> int:
    novos = 0
    for entrada in topico.pontos_de_vista:
        ponto = PontoDeVista.objects.filter(tenant=tenant, guid=entrada.guid).first()
        if ponto is None:
            ponto = PontoDeVista.objects.create(
                tenant=tenant, marcacao=marcacao, guid=entrada.guid, camera=entrada.camera,
            )
            novos += 1
        elif entrada.camera:
            ponto.camera = entrada.camera
            ponto.save(update_fields=["camera"])

        if entrada.snapshot and not ponto.snapshot and _imagem_valida(entrada.snapshot):
            nome = f"{entrada.guid}.png"
            ponto.snapshot.save(nome, ContentFile(entrada.snapshot), save=True)
    return novos


def _conciliar_comentarios(topico: bcf.TopicoBcf, marcacao: Marcacao, *, tenant) -> int:
    """Comentário só entra uma vez — o GUID é a trava.

    Sem ela, cada reimportação do mesmo arquivo empilharia a conversa inteira de
    novo, e o tópico de três respostas viraria um de trinta.
    """
    porcguid = {str(p.guid): p for p in marcacao.pontos_de_vista.all()}
    novos = 0
    for entrada in topico.comentarios:
        if ComentarioMarcacao.objects.filter(tenant=tenant, guid=entrada.guid).exists():
            continue
        ComentarioMarcacao.objects.create(
            tenant=tenant,
            marcacao=marcacao,
            guid=entrada.guid,
            texto=entrada.texto,
            autor=None,
            autor_nome=entrada.autor,
            ponto_de_vista=porcguid.get(entrada.ponto_de_vista_guid),
            criado_em=entrada.data or _agora(),
        )
        novos += 1
    return novos


def _valor_conhecido(bruto: str, choices, padrao: str) -> str:
    """Mapeia o valor do arquivo para o vocabulário do modelo.

    `TopicType`/`TopicStatus` são vocabulário **aberto** no BCF: cada ferramenta
    pode inventar o seu ("Assigned", "Verificado"). Cair no padrão é melhor que
    recusar o arquivo — o tópico entra e alguém o reclassifica —, mas o valor
    desconhecido vai para o log, porque um cliente cujo Solibri usa outro
    vocabulário aparecerá lá antes de aparecer como reclamação.
    """
    valores = {opcao.value for opcao in choices}
    if bruto in valores:
        return bruto
    if bruto:
        logger.info(
            "prancheta_bcf_valor_desconhecido",
            extra={"valor": bruto, "vocabulario": choices.__name__},
        )
    return padrao


def _usuario_do_email(email: str, tenant):
    """Casa o `AssignedTo` com um usuário do tenant, quando existir.

    É o que faz "atribuídas a mim" funcionar para a marcação que veio de fora.
    Escopado ao tenant explicitamente: um e-mail que existe em duas empresas não
    pode atribuir a marcação de uma à pessoa da outra.
    """
    if not email:
        return None
    from nucleo.models import Usuario

    return Usuario.objects.filter(tenant=tenant, email__iexact=email).first()


def _agora():
    from django.utils import timezone

    return timezone.now()
