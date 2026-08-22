# backend/funcoesimpexp/test_d70_portas_de_midia.py
"""D70 — a regressão que impede `/media/` de reabrir.

**O achado não foi um arquivo aberto; foi uma lista que crescia sozinha.** Todo
`upload_to` novo nascia servido por `/media/`, e o gateway só ficava sabendo
quando alguém lembrasse de conferir. A allowlist do nginx foi o remendo; este
teste é o que a torna desnecessária: ele varre **todos** os `FileField` dos
modelos instalados e cobra que cada prefixo tenha porta declarada.

Quem criar um `upload_to` novo vê este teste falhar com o nome do campo e do
prefixo — o que é a diferença entre descobrir na revisão e descobrir num
levantamento seis meses depois, que foi o que aconteceu.
"""
from __future__ import annotations

from django.apps import apps
from django.db import models
from django.test import SimpleTestCase

from .registro import NATUREZA_ARQUIVO, RecursoDesconhecido, obter

#: Prefixo de `upload_to` → o recurso que o entrega. **Esta tabela é o contrato**:
#: um prefixo que não estiver aqui derruba o teste, e a correção certa é dar-lhe
#: um recurso, não acrescentar uma linha.
PORTAS = {
    # RH — os quatro do levantamento de 09/08; ASO é dado de saúde (LGPD art. 11)
    "asos_funcionarios": "rh.aso",
    "holerites": "rh.holerite",
    "carteiras_trabalho": "rh.documentos",
    "documentos_funcionarios": "rh.documentos",
    # Cadastro e obra — fundação, sem entitlement
    "documentos_clientes": "cadastro.documento_cliente",
    "documentos_obras": "obra.documento",
    "diario_obra_media": "obra.diario_midia",
    # Fiscal — dois apps escrevem em `nfe_xmls/`, e por isso prefixo não é dono:
    # o `CustoEmpreendimento` tem gate próprio (`obra.custo_nfe`)
    "nfe_xmls": ("erp.nota_fiscal", "obra.custo_nfe"),
    "notas_fiscais": "erp.nota_fiscal",
    # Portas construídas antes do D70
    "impexp": "—",       # o próprio motor: entrada, conferência e saída
    "prancheta": ("prancheta.acervo", "prancheta.marcacao"),
}


def _prefixo(upload_to) -> str:
    """A primeira pasta de um `upload_to`, seja ele texto ou função.

    `upload_to` também aceita **callable** (é o caso do `nf_file_path` do ERP e
    do `caminho_revisao` da Prancheta), e aí não há string para ler. O nome da
    função não serve de prefixo, então quem é callable é resolvido pelo módulo
    que o declara — ver `_PREFIXO_DE_CALLABLE`.
    """
    if callable(upload_to):
        return _PREFIXO_DE_CALLABLE.get(upload_to.__name__, upload_to.__name__)
    return str(upload_to or "").strip("/").split("/")[0]


#: Callables de `upload_to` → a pasta que eles realmente escrevem. Curto de
#: propósito: se crescer, é sinal de que a convenção de caminho virou código
#: espalhado e merece uma função só.
_PREFIXO_DE_CALLABLE = {
    "nf_file_path": "notas_fiscais",      # moduloerp.models
    "caminho_revisao": "prancheta",       # moduloprancheta.models
    "caminho_snapshot": "prancheta",      # moduloprancheta.models
}


def _campos_de_arquivo():
    for modelo in apps.get_models():
        for campo in modelo._meta.get_fields():
            if isinstance(campo, models.FileField):
                yield modelo, campo


class TodoUploadTemPorta(SimpleTestCase):
    """O invariante do D70: nenhum `FileField` sem porta declarada."""

    def test_todo_upload_to_esta_na_tabela_de_portas(self):
        orfaos = [
            f"{modelo._meta.label}.{campo.name} → '{_prefixo(campo.upload_to)}/'"
            for modelo, campo in _campos_de_arquivo()
            if _prefixo(campo.upload_to) not in PORTAS
        ]
        self.assertFalse(
            orfaos,
            "FileField sem porta no funcoesimpexp — o arquivo sairia por `/media/`, "
            "que o gateway responde 404 (e que, num dev com DEBUG=True, entrega o "
            "binário fora de auth, entitlement e RLS). Declare um `Recurso` de "
            f"natureza 'arquivo' com `entregar_arquivo` e registre-o aqui: {orfaos}",
        )

    def test_os_recursos_declarados_existem_e_entregam(self):
        """Nome na tabela não basta — o recurso tem de existir e ter saída."""
        for prefixo, ids in PORTAS.items():
            if ids == "—":
                continue
            for recurso_id in (ids,) if isinstance(ids, str) else ids:
                with self.subTest(prefixo=prefixo, recurso=recurso_id):
                    try:
                        recurso = obter(recurso_id)
                    except RecursoDesconhecido:
                        self.fail(
                            f"'{prefixo}/' aponta para o recurso '{recurso_id}', que "
                            "ninguém registrou. O `impexp.py` do módulo não está sendo "
                            "carregado, ou o id mudou."
                        )
                    self.assertEqual(
                        recurso.natureza, NATUREZA_ARQUIVO,
                        f"'{recurso_id}' guarda binário e precisa ser de natureza arquivo.",
                    )
                    self.assertTrue(
                        recurso.entrega,
                        f"'{recurso_id}' não sobrescreve `entregar_arquivo` — não tem saída.",
                    )

    def test_a_entrega_tem_gate_de_leitura(self):
        """Recurso que entrega binário sem permissão exigida é porta aberta."""
        for prefixo, ids in PORTAS.items():
            if ids == "—":
                continue
            for recurso_id in (ids,) if isinstance(ids, str) else ids:
                with self.subTest(recurso=recurso_id):
                    recurso = obter(recurso_id)
                    self.assertTrue(
                        recurso.permissoes_da_entrega,
                        f"'{recurso_id}' entrega arquivo sem exigir permissão nenhuma.",
                    )
