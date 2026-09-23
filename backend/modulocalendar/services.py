# backend/modulocalendar/services.py
"""Feriados vindos de fora — o **plano B** do feed, não a fonte dele.

A fonte é a tabela `Feriado`, populada pelo comando `sincronizar_feriados`. Esta
função só existe para a instalação que ainda não sincronizou: sem ela, o
calendário do primeiro dia nasceria sem nenhum feriado nacional.

**Duas travas, e as duas vieram de um defeito medido (D147).** A chamada era
`requests.get(url)` — sem timeout e sem cache. Com a rede lenta ou a Nager fora
do ar, o feed inteiro do mês ficava pendurado no tempo de conexão padrão do
sistema operacional, que são minutos; e mesmo com a rede boa, cada navegação de
mês repetia a viagem. Agora:

- **timeout** — o mesmo `GEO_TIMEOUT` das outras chamadas de terceiro
  (`nucleo/geo.py`): provedor externo que não responde degrada, não trava;
- **cache** — o feriado nacional de um ano que já passou a existir não muda.
  Guardar por um dia transforma N navegações de mês em uma viagem. O negativo
  (falhou, ou o ano não existe na fonte) é guardado por pouco tempo, para a
  indisponibilidade de agora não virar um dia sem plano B.
"""
import logging

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

#: Desempenho, não teto de uso (§5.6 do `payment/planos.py`): o dado é público,
#: estável e de um ano inteiro. Um dia no positivo; dez minutos no negativo.
CACHE_TTL = 60 * 60 * 24
CACHE_TTL_NEGATIVO = 60 * 10


def get_holidays(year, country_code):
    """Feriados nacionais do ano na Nager.Date. Lista vazia se não deu."""
    chave = f"calendar:nager:{country_code}:{year}"
    cacheado = cache.get(chave)
    if cacheado is not None:
        return cacheado

    url = f"https://date.nager.at/api/v3/PublicHolidays/{year}/{country_code}"
    try:
        response = requests.get(url, timeout=getattr(settings, "GEO_TIMEOUT", (5, 15)))
        response.raise_for_status()
        holidays = response.json()
    except (requests.RequestException, ValueError) as e:
        logger.warning("Nager.Date falhou para %s/%s: %s", country_code, year, e)
        cache.set(chave, [], CACHE_TTL_NEGATIVO)
        return []

    if not isinstance(holidays, list):
        cache.set(chave, [], CACHE_TTL_NEGATIVO)
        return []
    logger.info("%s feriados encontrados para %s em %s.", len(holidays), country_code, year)
    cache.set(chave, holidays, CACHE_TTL if holidays else CACHE_TTL_NEGATIVO)
    return holidays
