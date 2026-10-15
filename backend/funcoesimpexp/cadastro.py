# backend/funcoesimpexp/cadastro.py
"""Recurso de cadastro — uma linha do arquivo, um registro do model.

**Por que uma base, e não seis declarações escritas à mão** (14/10/2026). Os
cadastros (cliente, fornecedor, funcionário, cargo, obra, empreendimento,
entidade) pedem a mesma coisa ao motor: achar pela chave, validar como a tela
valida, criar, desfazer apagando, respeitar a quota do plano e exportar o recorte
da lista. Escrito seis vezes, cada um esqueceria uma parte diferente — e a parte
esquecida seria a porta por onde o dado estranho entra.

**Importar só cria.** É a regra do dono e o motor já a garante (a linha que já
existe trava o lote); aqui `aplicar_linha` só sabe criar. Editar é pela tela.

**A validação é a do model**, não uma terceira cópia da regra: `full_clean` roda
os validadores do campo (CPF só com dígitos, e-mail bem formado, escolha fora da
lista, campo obrigatório) e a unicidade por tenant é conferida aqui com a frase
que a pessoa entende — a mensagem padrão do Django para restrição condicional é
*"Constraint … is violated"*, que não diz nada a quem preencheu a planilha.
"""
from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError, Q, RestrictedError, UniqueConstraint

from .formatos.leitura import normalizar
from .importacao import ImportacaoInvalida, LimiteDoPlano
from .registro import Recurso


class RecursoDeLista(Recurso):
    """Só a saída: a lista da tela vira planilha, no recorte que a tela mostra.

    **Por que separado do cadastro** (decisão do dono, 15/10/2026): toda lista
    exporta, mas documento de fluxo — pedido, cotação, boleto, nota, medição,
    contrato, diário — **não importa**: nasce pela tela, com aprovação e
    efeitos. Sem `aplicar_linha`, o motor não oferece o Importar.

    `colunas` aceita caminho (`fornecedor__razao_social`) e propriedade do
    model; a escolha sai pelo rótulo. Gancho opcional: `escopo` (o que esta
    pessoa enxerga na tela, além do tenant).
    """

    #: A classe do ORM. Obrigatória.
    modelo = None
    #: Ordem da exportação.
    ordem: tuple[str, ...] = ()
    #: Colunas que apontam para outro cadastro **pelo nome**: `campo da FK ->
    #: (model, campo do nome)`. Na planilha o cargo é "Pedreiro", não `cargo_id
    #: = 7`; o nome que não existe no tenant trava a linha, em vez de entrar
    #: vazio — e o que sai é o nome, para o arquivo poder voltar.
    referencias: dict = {}
    #: R7 — os campos que a busca da tela percorre (`?search=` ou `?busca=`).
    campos_de_busca: tuple[str, ...] = ()
    #: `True` = cada palavra casa em algum campo (o `SearchFilter` do DRF, nas
    #: telas que buscam no servidor); `False` = a frase inteira num campo (o
    #: `contemSemAcento` das telas que filtram no navegador). Tem de ser o que a
    #: tela faz, senão o arquivo traz outro conjunto.
    busca_por_palavra: bool = True
    #: R7 — filtros exatos da tela: `parâmetro -> lookup do ORM`.
    filtros: dict = {}

    # ------------------------------------------------------------------
    # Ganchos do módulo
    # ------------------------------------------------------------------

    def escopo(self, qs, request):
        """O que esta pessoa enxerga na tela, além do tenant (o padrão é tudo)."""
        return qs

    def recortar(self, qs, recorte: dict, request):
        """R7 — os filtros da tela: a busca sem acento e os filtros exatos.

        Parâmetro que a declaração não conhece é ignorado, e não erro: a tela
        manda o estado inteiro dela (ordem, página), e o que não é filtro não
        muda o conjunto.
        """
        for parametro, lookup in self.filtros.items():
            valor = recorte.get(parametro)
            if valor not in (None, ""):
                qs = qs.filter(**{lookup: valor})
        # Como a `BuscaSemAcento` da tela (o `SearchFilter` do DRF): cada palavra
        # tem de casar em algum campo. Uma frase inteira num `icontains` só
        # devolveria menos do que a tela mostra — e a R7 é "o mesmo recorte".
        busca = str(recorte.get("search") or recorte.get("busca") or "").strip()
        if self.campos_de_busca and busca:
            termos = busca.replace(",", " ").split() if self.busca_por_palavra else [busca]
            for palavra in termos:
                condicao = Q()
                for campo in self.campos_de_busca:
                    condicao |= Q(**{f"{campo}__unaccent__icontains": palavra})
                qs = qs.filter(condicao)
        return qs

    # ------------------------------------------------------------------
    # Saída
    # ------------------------------------------------------------------

    def ordem_padrao(self) -> tuple[str, ...]:
        return self.ordem or ("pk",)

    def queryset(self, request, recorte: dict):
        tenant_id = getattr(getattr(request.user, "tenant", None), "id", None)
        qs = self.modelo._default_manager.filter(tenant_id=tenant_id)
        qs = self.escopo(qs, request)
        qs = self.recortar(qs, recorte, request)
        return qs.order_by(*self.ordem_padrao())

    def serializar_objeto(self, obj) -> dict:
        """A escolha sai pelo rótulo e a referência pelo nome — o que a pessoa lê,
        e o que a volta aceita. `a__b` segue a relação; vazio no meio é vazio."""
        saida = {}
        for coluna in self.colunas:
            if coluna.campo in self.referencias:
                alvo = getattr(obj, coluna.campo, None)
                saida[coluna.campo] = getattr(alvo, self.referencias[coluna.campo][1], "") if alvo else ""
                continue
            *caminho, ultimo = coluna.campo.split("__")
            dono = obj
            for passo in caminho:
                dono = getattr(dono, passo, None) if dono is not None else None
            if dono is None:
                saida[coluna.campo] = None
                continue
            exibir = getattr(dono, f"get_{ultimo}_display", None)
            saida[coluna.campo] = exibir() if callable(exibir) else getattr(dono, ultimo, None)
        return saida


class RecursoDeCadastro(RecursoDeLista):
    """Declare `modelo`, `colunas`, `chave` e as permissões; o resto vem pronto.

    Ganchos opcionais: `campos` (dados do arquivo → campos do model),
    `normalizar_chave`, `validar_regras` (regra do módulo que precisa do objeto),
    `recortar` (os filtros da tela — R7) e `depois_de_criar`.
    """

    #: Campo do model que guarda a chave, quando o nome difere do da coluna.
    campo_da_chave: str = ""
    #: Quota de `nucleo.quotas` que conta este cadastro ("clientes", "obras"…).
    #: Vazio = cadastro sem teto de plano.
    quota: str = ""
    #: Campos do model que `full_clean` não confere — preenchidos pelo sistema
    #: depois, ou que não vêm do arquivo.
    nao_validar: tuple[str, ...] = ()

    def ordem_padrao(self) -> tuple[str, ...]:
        return self.ordem or (self.campo_da_chave or self.chave,)

    # ------------------------------------------------------------------
    # Ganchos do módulo
    # ------------------------------------------------------------------

    def normalizar_chave(self, valor) -> str:
        return str(valor or "").strip()

    def chave_da_linha(self, dados: dict) -> str:
        return self.normalizar_chave(dados.get(self.chave))

    def campos(self, dados: dict, tenant_id) -> dict:
        """Dados do arquivo → `campo -> valor` do model.

        O padrão copia as colunas cujo `campo` é campo do model, troca vazio por
        `None` onde o campo aceita nulo, traduz o **rótulo** de uma escolha para
        o código — a exportação sai legível ("Solteiro(a)"), e a planilha que
        volta com esse texto tem de entrar — e resolve as `referencias` pelo nome.
        """
        nomes = {f.name: f for f in self.modelo._meta.concrete_fields}
        saida = {}
        for coluna in self.colunas:
            campo = nomes.get(coluna.campo)
            if campo is None:
                continue
            valor = dados.get(coluna.campo)
            if coluna.campo in self.referencias:
                saida[coluna.campo] = self._referencia(coluna.campo, valor, tenant_id)
                continue
            if coluna.campo == (self.campo_da_chave or self.chave):
                valor = self.normalizar_chave(valor)
            if valor == "" and campo.null:
                valor = None
            if valor not in (None, "") and campo.choices:
                valor = _codigo_da_escolha(campo, valor)
            saida[coluna.campo] = valor
        return saida

    def validar_regras(self, objeto, dados: dict, tenant_id) -> str:
        """Regra do módulo que precisa do objeto montado. "" = passa."""
        return ""

    def depois_de_criar(self, objeto, dados: dict, tenant_id) -> None:
        """Efeito do módulo depois de gravar (aviso a outro módulo, por exemplo)."""

    # ------------------------------------------------------------------
    # Entrada
    # ------------------------------------------------------------------

    def localizar(self, dados: dict, tenant_id):
        chave = self.normalizar_chave(dados.get(self.chave))
        if not chave:
            return None
        return self.modelo._default_manager.filter(
            tenant_id=tenant_id, **{self.campo_da_chave or self.chave: chave},
        ).first()

    def validar_no_destino(self, dados: dict, tenant_id) -> str:
        ausente = self._referencia_ausente(dados, tenant_id)
        if ausente:
            return ausente
        objeto = self.modelo(tenant_id=tenant_id, **self.campos(dados, tenant_id))
        repetido = self._unicidade(objeto, tenant_id)
        if repetido:
            return repetido
        try:
            objeto.full_clean(
                exclude=("tenant", *self.nao_validar), validate_constraints=False,
            )
        except ValidationError as exc:
            return self._frase(exc)
        return self.validar_regras(objeto, dados, tenant_id)

    def aplicar_linha(self, dados: dict, existente, tenant_id) -> dict:
        ausente = self._referencia_ausente(dados, tenant_id)
        if ausente:
            # O cargo que existia na conferência foi excluído antes do "sim".
            raise ImportacaoInvalida(f"{ausente} Nada foi importado.")
        objeto = self.modelo(tenant_id=tenant_id, **self.campos(dados, tenant_id))
        try:
            # Ponto de salvamento: sem ele a violação apodrece a transação do
            # lote inteiro e a mensagem que sobe é a do banco, não a nossa.
            with transaction.atomic():
                objeto.save()
        except IntegrityError as exc:
            raise ImportacaoInvalida(
                f"“{self.normalizar_chave(dados.get(self.chave))}” conflita com outra linha "
                "do arquivo (algum campo que não pode se repetir) — nada foi importado."
            ) from exc
        self.depois_de_criar(objeto, dados, tenant_id)
        return {"acao": "criou", "pk": objeto.pk}

    def desfazer_linha(self, estado_anterior: dict, tenant_id) -> None:
        objeto = self.modelo._default_manager.filter(
            pk=estado_anterior.get("pk"), tenant_id=tenant_id,
        ).first()
        if objeto is None:
            return
        try:
            with transaction.atomic():
                objeto.delete()
        except (ProtectedError, RestrictedError, IntegrityError) as exc:
            raise ImportacaoInvalida(
                f"“{objeto}” já está em uso no sistema — o lote não pode mais ser desfeito. "
                "Exclua pela tela o que não quiser manter."
            ) from exc

    def checar_quota_objeto(self, novas: int, limites: dict | None, tenant_id) -> None:
        if not self.quota or not isinstance(limites, dict):
            return
        limite = limites.get(self.quota)
        if not isinstance(limite, int) or limite < 0:
            return
        from nucleo.quotas import ROTULOS, uso_atual

        atual = uso_atual(self.quota, tenant_id)
        if atual + novas <= limite:
            return
        rotulo = ROTULOS.get(self.quota, self.quota)
        raise LimiteDoPlano(
            f"O plano inclui {limite} {rotulo}; a empresa já tem {atual} e este arquivo "
            f"traria mais {novas}. Exclua o que não usa ou faça upgrade do plano.",
            limite=limite, tentado=atual + novas, quota=self.quota,
        )

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------

    def _candidatos(self, campo: str, valor, tenant_id):
        modelo, nome = self.referencias[campo]
        texto = str(valor or "").strip()
        if not texto:
            return texto, []
        return texto, list(
            modelo._default_manager.filter(tenant_id=tenant_id, **{f"{nome}__iexact": texto})[:2]
        )

    def _referencia(self, campo: str, valor, tenant_id):
        _, achados = self._candidatos(campo, valor, tenant_id)
        return achados[0] if len(achados) == 1 else None

    def _referencia_ausente(self, dados: dict, tenant_id) -> str:
        """O primeiro nome que não aponta para exatamente um cadastro do tenant."""
        for campo in self.referencias:
            texto, achados = self._candidatos(campo, dados.get(campo), tenant_id)
            if not texto:
                continue
            rotulo = self._rotulo(campo)
            if not achados:
                return f"{rotulo} “{texto}” não existe — cadastre antes de importar."
            if len(achados) > 1:
                return f"{rotulo} “{texto}” é ambíguo: há mais de um com esse nome."
        return ""

    def _unicidade(self, objeto, tenant_id) -> str:
        """As restrições `(tenant, campo…)` do model, com a frase de quem preencheu.

        Quem decide se há violação é o próprio Django (`UniqueConstraint.validate`),
        que respeita a **condição** da restrição — a obra tem duas, "nome único no
        empreendimento" e "nome único quando não há empreendimento", e conferir
        só os campos aplicaria a segunda a toda obra. Daqui sai só a frase: a
        padrão para restrição condicional é *"Constraint … is violated"*.
        """
        for restricao in self.modelo._meta.constraints:
            if not isinstance(restricao, UniqueConstraint) or "tenant" not in restricao.fields:
                continue
            try:
                restricao.validate(self.modelo, objeto)
            except ValidationError:
                outros = [f for f in restricao.fields if f != "tenant"]
                nomes = ", ".join(self._rotulo(f) for f in outros)
                texto = ", ".join(str(getattr(objeto, f, "") or "—") for f in outros)
                return f"Já existe outro cadastro com este {nomes}: “{texto}”."
        return ""

    def _rotulo(self, campo: str) -> str:
        coluna = self.coluna_por_campo(campo)
        if coluna:
            return coluna.rotulo
        return str(self.modelo._meta.get_field(campo).verbose_name)

    def _frase(self, exc: ValidationError) -> str:
        if hasattr(exc, "message_dict"):
            for campo, mensagens in exc.message_dict.items():
                if campo == "__all__":
                    return mensagens[0]
                return f"{self._rotulo(campo)}: {mensagens[0]}"
        return exc.messages[0] if exc.messages else "Linha inválida."


_SIM = {"sim", "s", "1", "true", "x", "verdadeiro"}
_NAO = {"nao", "n", "0", "false", "falso"}


def sim_ou_nao(valor, padrao: bool):
    """Coluna Sim/Não da planilha: em branco é o `padrao` da ficha; o que não for
    sim nem não devolve `None`, e quem chama trava a linha dizendo o que veio."""
    texto = normalizar(valor)
    if not texto:
        return padrao
    if texto in _SIM:
        return True
    if texto in _NAO:
        return False
    return None


def _codigo_da_escolha(campo, valor):
    """'Solteiro(a)' ou 'solteiro' → 'solteiro'. Sem casar, devolve o que veio —
    e o `full_clean` recusa com "não é uma opção válida"."""
    alvo = normalizar(valor)
    for codigo, rotulo in campo.flatchoices:
        if alvo in (normalizar(codigo), normalizar(rotulo)):
            return codigo
    return valor
