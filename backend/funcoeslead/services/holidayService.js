// backend/funcoeslead/services/holidayService.js
const axios = require('axios');
const logger = require('../logger');

/**
 * Busca feriados para um determinado ano e país.
 * @param {number} year O ano para o qual buscar os feriados.
 * @param {string} countryCode O código do país (ex: 'BR').
 * @returns {Promise<Array>} Uma lista de feriados.
 */
async function getHolidays(year, countryCode) {
    const url = `https://date.nager.at/api/v3/PublicHolidays/${year}/${countryCode}`;
    logger.info(`Buscando feriados em: ${url}`);

    try {
        const response = await axios.get(url);
        logger.info(`Encontrados ${response.data.length} feriados para ${countryCode} em ${year}.`);
        return response.data;
    } catch (error) {
        logger.error(`Erro ao buscar feriados da API Nager.Date para ${countryCode}/${year}:`, error.message);
        // Retorna um array vazio em caso de erro para não quebrar o fluxo principal
        return [];
    }
}

module.exports = {
    getHolidays,
};
