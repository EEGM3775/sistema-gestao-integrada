# backend/modulocalendar/services.py
import requests
import logging

logger = logging.getLogger(__name__)

def get_holidays(year, country_code):
    """
    Busca feriados de uma API externa (Nager.Date).
    """
    url = f"https://date.nager.at/api/v3/PublicHolidays/{year}/{country_code}"
    try:
        response = requests.get(url)
        response.raise_for_status()  # Lança uma exceção para respostas de erro (4xx ou 5xx)
        holidays = response.json()
        logger.info(f"{len(holidays)} feriados encontrados para {country_code} em {year}.")
        return holidays
    except requests.exceptions.RequestException as e:
        logger.error(f"Erro ao buscar feriados da API Nager.Date: {e}")
        return []
