"""Completa o endereço dos clientes de demonstração com endereços que existem.

    python manage.py completar_enderecos_demo --tenant demo
    python manage.py completar_enderecos_demo --tenant demo --simular

**Por quê.** A carteira de demonstração (`semear_carteira_demo`) nasceu só com
cidade e UF: nenhum dos 2.004 clientes tinha CEP, e só 4 tinham rua. Nota fiscal
(a prefeitura exige CEP e o código IBGE do tomador) e boleto registrado no banco
(CNAB exige endereço completo do pagador) ficavam impossíveis de testar — itens
52 e 58 do dono, 30/09/2026.

**Endereços reais, não inventados.** Para cada cidade da carteira, o comando
busca no ViaCEP ruas de verdade daquela cidade (logradouro, bairro, CEP e o
código IBGE oficial) e sorteia uma para cada cliente, com número aleatório. O
sorteio usa `--semente`, então rodar de novo dá o mesmo resultado.

**O que ele não toca.** CPF/CNPJ (os da demonstração já são válidos), cliente
que já tem CEP, e cadastro do Asaas: grava por `bulk_update`, sem os sinais que
sincronizariam os clientes com o gateway.

**Dev/staging apenas** — recusa rodar com `DEBUG=False` sem `--sei-o-que-faco`.
"""
from __future__ import annotations

import random
import unicodedata
from collections import defaultdict

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from nucleo.models import Tenant
from nucleo.tenancy import tenant_context

VIACEP = "https://viacep.com.br/ws"
OVERPASS = "https://overpass-api.de/api/interpreter"
# Abaixo disso a cidade quase certamente tem CEP único e o ViaCEP não lista as
# ruas — a carteira ficaria amontoada em duas ou três.
MINIMO_DE_RUAS = 50
# Palavras que aparecem em nome de rua em qualquer cidade brasileira: cada uma
# devolve até 50 endereços do ViaCEP, e juntas dão variedade para a carteira.
TERMOS = ["Rua", "Avenida", "Servidao", "Jose", "Joao", "Maria", "Santa", "Sao", "Antonio",
          "Manoel", "Francisco", "Pedro", "Paulo", "Santos", "Silva", "Brasil", "Flores"]


def _sem_acento(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()


class Command(BaseCommand):
    help = "Completa endereço, CEP e código IBGE dos clientes de demonstração com endereços reais (ViaCEP)."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", default="demo", help="Slug do tenant (padrão: demo)")
        parser.add_argument("--semente", type=int, default=51, help="Semente do sorteio (reprodutível)")
        parser.add_argument("--simular", action="store_true", help="Só mostra o que faria")
        parser.add_argument("--sei-o-que-faco", action="store_true", dest="forcar",
                            help="Permite rodar com DEBUG=False (staging)")

    def handle(self, *args, **opts):
        if not settings.DEBUG and not opts["forcar"]:
            raise CommandError("Comando de demonstração: com DEBUG=False, rode com --sei-o-que-faco.")
        tenant = Tenant.objects.filter(slug=opts["tenant"]).first()
        if tenant is None:
            raise CommandError(f"Tenant '{opts['tenant']}' não existe.")
        sorteio = random.Random(opts["semente"])

        from clientes.models import Cliente

        with tenant_context(tenant.pk):
            pendentes = [
                c for c in Cliente._base_manager.filter(tenant=tenant).order_by("pk")
                if len("".join(ch for ch in (c.cep or "") if ch.isdigit())) != 8
            ]
            por_cidade = defaultdict(list)
            for c in pendentes:
                por_cidade[((c.estado or "").upper(), c.cidade or "")].append(c)

            alterados, sem_endereco = [], []
            for (uf, cidade), clientes in sorted(por_cidade.items()):
                enderecos = self._enderecos(uf, cidade)
                if not enderecos:
                    sem_endereco.append(f"{cidade}/{uf} ({len(clientes)})")
                    continue
                self.stdout.write(f"{cidade}/{uf}: {len(clientes)} clientes, {len(enderecos)} ruas reais")
                for c in clientes:
                    e = sorteio.choice(enderecos)
                    c.endereco = e["logradouro"]
                    c.numero_endereco = str(sorteio.randint(1, 1999))
                    c.bairro = e["bairro"] or c.bairro or "Centro"
                    c.cep = e["cep"].replace("-", "")
                    c.cidade = e["localidade"]
                    c.estado = e["uf"]
                    c.cidade_ibge = e["ibge"]
                    alterados.append(c)

            if sem_endereco:
                self.stdout.write(self.style.WARNING(f"Sem endereço no ViaCEP: {', '.join(sem_endereco)}"))
            if opts["simular"]:
                for c in alterados[:5]:
                    self.stdout.write(f"  {c.nome_completo}: {c.endereco}, {c.numero_endereco} — {c.bairro} — "
                                      f"{c.cep} {c.cidade}/{c.estado} (IBGE {c.cidade_ibge})")
                self.stdout.write(self.style.WARNING(f"Simulação: {len(alterados)} clientes seriam completados."))
                return
            Cliente._base_manager.bulk_update(
                alterados, ["endereco", "numero_endereco", "bairro", "cep", "cidade", "estado", "cidade_ibge"],
                batch_size=500,
            )
            faltando = sum(
                1 for c in Cliente._base_manager.filter(tenant=tenant).only("cep")
                if len("".join(ch for ch in (c.cep or "") if ch.isdigit())) != 8
            )
        self.stdout.write(self.style.SUCCESS(
            f"{len(alterados)} clientes completados; sem CEP agora: {faltando}."
        ))

    def _enderecos(self, uf: str, cidade: str) -> list[dict]:
        saida = self._pelo_viacep(uf, cidade)
        if len(saida) < MINIMO_DE_RUAS:
            saida += self._cep_unico(uf, cidade, saida)
        return saida

    def _cep_unico(self, uf: str, cidade: str, conhecidos: list[dict]) -> list[dict]:
        """Cidade pequena tem **um CEP para o município inteiro** (ex.: Garopaba,
        88495-000), e o ViaCEP só lista as poucas ruas com CEP próprio. As outras
        ruas continuam existindo: os nomes vêm do OpenStreetMap, e o CEP é o
        geral da cidade, que é o endereçamento correto para elas."""
        if not conhecidos:
            return []
        geral = conhecidos[0]["cep"].replace("-", "")[:5] + "000"
        try:
            base = requests.get(f"{VIACEP}/{geral}/json/", timeout=10).json()
        except (requests.RequestException, ValueError):
            return []
        if base.get("erro") or _sem_acento(base.get("localidade", "")).lower() != _sem_acento(cidade).lower():
            return []
        consulta = (
            f'[out:json][timeout:30];area["name"="{cidade}"]["admin_level"="8"]->.a;'
            'way(area.a)[highway~"residential|primary|secondary|tertiary|unclassified"][name];out tags;'
        )
        try:
            resp = requests.post(OVERPASS, data={"data": consulta}, timeout=60,
                                 headers={"User-Agent": "sgi-plataforma/1.0 (demo)"})
            nomes = sorted({e["tags"]["name"] for e in resp.json().get("elements", [])})
        except (requests.RequestException, ValueError, KeyError):
            return []
        self.stdout.write(f"  {cidade}/{uf}: CEP único {base['cep']} + {len(nomes)} ruas do OpenStreetMap")
        return [
            {"logradouro": n, "bairro": "", "cep": base["cep"], "localidade": base["localidade"],
             "uf": base["uf"], "ibge": base["ibge"]}
            for n in nomes
        ]

    def _pelo_viacep(self, uf: str, cidade: str) -> list[dict]:
        """Ruas reais da cidade, sem repetir CEP e só com logradouro e bairro."""
        vistos, saida = set(), []
        for termo in TERMOS:
            try:
                resp = requests.get(f"{VIACEP}/{uf}/{_sem_acento(cidade)}/{termo}/json/", timeout=10)
                itens = resp.json() if resp.status_code == 200 else []
            except (requests.RequestException, ValueError):
                continue
            for e in itens if isinstance(itens, list) else []:
                if e.get("cep") in vistos or not e.get("logradouro") or not e.get("ibge"):
                    continue
                vistos.add(e["cep"])
                saida.append(e)
        return saida
