# backend/moduloprancheta/motores/ifc.py
"""Motor `ifcopenshell` — IFC para glTF, o 3D que abre no celular.

**IFC é o formato livre e maduro do BIM** (planta §4), e é por isso que ele é o
único 3D que a Prancheta abre sem depender da Autodesk. O caminho tem duas
metades, e elas falham por motivos diferentes:

- **ler o modelo** (`ifcopenshell.open`) é Python sobre o parser do schema —
  barato, estável entre versões, e é de onde saem os metadados que o acervo
  mostra (schema, nome do projeto, quantos elementos);
- **tesselar a geometria** (`ifcopenshell.geom`) usa o wrapper compilado e é a
  parte pesada — um IFC de 2 GB vira dezenas de MB de malha, e a API do
  serializador mudou entre a 0.7 e a 0.8.

O código trata as duas separadamente de propósito: um IFC cujo wrapper não
tesselou ainda rende metadado útil, e a falha diz *qual* metade falhou em vez de
"erro na conversão".

**Sobre o alvo:** a planta §4 cita *That Open / Fragments* no browser, que é o
formato que comprime melhor. Fragments, porém, é gerado por biblioteca **JS** —
plugá-lo aqui significaria pôr Node no backend de novo, contra a Fase 11 inteira,
que acabou de tirá-lo. glTF é o denominador aberto que o `web-ifc`/Fragments
consome e que qualquer viewer 3D abre; se a PRA.2 medir que o ganho de Fragments
compensa, a conversão é um passo **do frontend** sobre o glTF, não um serviço
novo aqui.

**Licenças:** IfcOpenShell é LGPL e entra como biblioteca Python — sem a
obrigação de redistribuição que o LibreDWG traz (ver `dwg.py`).
"""
from __future__ import annotations

import os
import tempfile

from payment.planos import PRANCHETA_TETO_ELEMENTOS_IFC

from .base import (
    NAO_EMBRULHAR,
    Adaptador,
    ArquivoCorrompido,
    FalhaMotor,
    MotorIndisponivel,
    Saida,
    versao_de_modulo,
)

#: Teto de elementos tesselados numa conversão: o ponto a partir do qual um único
#: IFC monopoliza o worker por dezenas de minutos e atrasa a fila de todos os
#: tenants. Acima dele a resposta honesta é dizer que o modelo é grande demais
#: para este caminho — o upload retomável e a tesselação em partes são trabalho da
#: mesma fatia que subir o teto de 300 MB.
#:
#: **O número mora em [payment/planos.py](../../../payment/planos.py) §5.4.** O
#: comentário aqui dizia "não é limite de plano", e a decisão do dono de 08/08/2026
#: respondeu a isso: é COGS de *tempo* de worker compartilhado, e todo teto vive
#: em `payment/` — inclusive o que ninguém compra, porque é lá que ele é visto.
TETO_ELEMENTOS = PRANCHETA_TETO_ELEMENTOS_IFC


class MotorIfc(Adaptador):
    codigo = "ifcopenshell"
    tipos = ("modelo_3d",)

    def _detectar_versao(self) -> str:
        versao = versao_de_modulo("ifcopenshell")
        return f"ifcopenshell-{versao}" if versao else ""

    def converter(self, caminho: str, *, formato: str, tipo: str, economia: str = "",
                  teto_snap: int | None = 0, retomada=None, prazo=None) -> Saida:
        # `retomada`/`prazo` ignorados: `retomavel = False` (PRA.11). A unidade
        # retomável aqui seria o elemento tesselado, não a folha — o modelo sai
        # num glTF só —, e parar no meio dele não produz nada que se possa abrir.
        # O teto de elementos do `planos.py` continua sendo a resposta.
        # `economia` ignorado: o custo aqui é a tesselação do OpenCascade, e não
        # há knob que a reduza sem entregar um sólido que não é o do arquivo.
        # `economias` vazio, então o pipeline não desce escada nenhuma.
        modelo, metadados = self._abrir(caminho)
        conteudo = self._para_gltf(caminho, modelo)
        return Saida(
            conteudo=conteudo,
            extensao="glb",
            content_type="model/gltf-binary",
            detalhe=metadados,
        )

    # -- metade barata: o modelo e o que ele diz de si -----------------------
    def _abrir(self, caminho: str):
        try:
            import ifcopenshell
        except Exception as exc:
            raise MotorIndisponivel(
                "A biblioteca `ifcopenshell` não está instalada nesta imagem."
            ) from exc

        try:
            modelo = ifcopenshell.open(caminho)
        except NAO_EMBRULHAR:
            # O teto agindo — ver `NAO_EMBRULHAR`. O parser carrega o arquivo
            # inteiro antes de o `TETO_ELEMENTOS` abaixo ter o que contar, então
            # é aqui que um IFC grande estoura, e não na contagem.
            raise
        except Exception as exc:
            raise ArquivoCorrompido(f"IFC ilegível: {exc}") from exc

        produtos = modelo.by_type("IfcProduct")
        if len(produtos) > TETO_ELEMENTOS:
            raise FalhaMotor(
                f"O modelo tem {len(produtos):,} elementos, acima do teto de "
                f"{TETO_ELEMENTOS:,} desta etapa da conversão.".replace(",", ".")
            )

        projetos = modelo.by_type("IfcProject")
        return modelo, {
            "schema": getattr(modelo, "schema", ""),
            "projeto": getattr(projetos[0], "Name", "") if projetos else "",
            "elementos": len(produtos),
        }

    # -- metade cara: a geometria --------------------------------------------
    def _para_gltf(self, caminho: str, modelo) -> bytes:
        """Tessela e serializa em glTF binário.

        A assinatura do serializador mudou entre as séries do IfcOpenShell (a 0.8
        acrescentou um segundo objeto de configuração). Em vez de fixar uma
        versão no `requirements` e quebrar no próximo upgrade, tentamos a
        assinatura nova e caímos na antiga — o `motor_versao` carimbado na
        derivada registra qual atendeu, que é o que permite invalidar o acervo
        por comparação depois.
        """
        try:
            import ifcopenshell.geom as geom
        except Exception as exc:
            raise MotorIndisponivel(
                "Este `ifcopenshell` não traz o módulo de geometria (`geom`) — "
                "é a metade compilada, que falta em builds só-parser."
            ) from exc

        ajustes = geom.settings()
        # Coordenadas de mundo: sem isso cada elemento sai na origem local e o
        # modelo aparece todo empilhado no centro — o sintoma clássico, e que
        # parece defeito de viewer.
        for chave in ("use-world-coords", "USE_WORLD_COORDS"):
            try:
                ajustes.set(getattr(ajustes, chave, chave), True)
                break
            except Exception:
                continue

        descritor, destino = tempfile.mkstemp(suffix=".glb", prefix="prancheta-")
        os.close(descritor)
        serializador = None
        try:
            serializador = self._serializador(geom, destino, ajustes)
            serializador.setFile(modelo)
            serializador.setUnitNameAndMagnitude("METER", 1.0)
            serializador.writeHeader()

            iterador = geom.iterator(ajustes, modelo)
            if not iterador.initialize():
                raise FalhaMotor("Nenhuma geometria tesselável no modelo.")
            while True:
                serializador.write(iterador.get())
                if not iterador.next():
                    break
            serializador.finalize()

            # **O `.glb` só existe depois que o serializador morre.** O
            # serializador glTF acumula a malha em dois arquivos vizinhos
            # (`.glb.vertices.tmp` e `.glb.indices.tmp`) e monta o binário final
            # no destrutor C++, não no `finalize()` — que apesar do nome apenas
            # fecha a coleta. Ler o arquivo com o objeto ainda vivo devolvia
            # SEMPRE zero byte, e o zero caía no `if not conteudo` lá embaixo:
            # todo IFC virava "a tesselação terminou sem produzir geometria",
            # uma frase que descreve um modelo vazio e mandava o cliente
            # procurar defeito no arquivo dele. Soltar a referência aqui é o que
            # transforma os dois `.tmp` no `.glb`.
            del serializador
            serializador = None

            with open(destino, "rb") as arquivo:
                conteudo = arquivo.read()
        except NAO_EMBRULHAR:
            # **O ponto mais caro do buraco que a promoção do `NAO_EMBRULHAR`
            # fechou.** Este `except` só relembrava `FalhaMotor`, então o teto do
            # D57 caía no genérico abaixo e virava `FalhaMotor` — que é
            # `retentavel`: a DLQ repetia **três vezes** uma tesselação que
            # reproduz o mesmo estouro, e cada repetição custa o mesmo pico de
            # memória. `NAO_EMBRULHAR` subsume o `FalhaMotor` que estava aqui.
            raise
        except Exception as exc:
            raise FalhaMotor(f"Falha ao tesselar o IFC: {exc}") from exc
        finally:
            # Solta o serializador também no caminho de erro: sem isso ele
            # sobreviveria à exceção e escreveria o `.glb` depois da faxina.
            del serializador
            for sufixo in ("", ".vertices.tmp", ".indices.tmp"):
                try:
                    os.unlink(destino + sufixo)
                except OSError:  # pragma: no cover - já removido ou nunca criado
                    pass

        if not conteudo:
            raise FalhaMotor("A tesselação terminou sem produzir geometria.")
        return conteudo

    def _serializador(self, geom, destino: str, ajustes):
        try:
            return geom.serializers.gltf(destino, ajustes, geom.serializer_settings())
        except (AttributeError, TypeError):
            pass
        try:
            return geom.serializers.gltf(destino, ajustes)
        except Exception as exc:
            raise MotorIndisponivel(
                "Este build do `ifcopenshell` não traz o serializador glTF."
            ) from exc
