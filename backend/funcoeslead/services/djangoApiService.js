// backend/funcoeslead/services/djangoApiService.js
const axios = require('axios');
const config = require('../config');
const logger = require('../logger');

const apiClient = axios.create({
    baseURL: config.djangoApiUrl,
    headers: {
        'Authorization': `Token ${config.djangoApiToken}`,
        'Content-Type': 'application/json'
    }
});

/**
 * Busca um objeto da API do Django.
 * @param {string} endpoint O endpoint da API (ex: '/crm/leads/').
 * @param {string} id O ID do objeto.
 * @returns {Promise<object>} O objeto da API.
 */
const getObject = async (endpoint, id) => {
    try {
        const response = await apiClient.get(`${endpoint}${id}/`);
        logger.info(`Objeto ${id} buscado com sucesso de ${endpoint}`);
        return response.data;
    } catch (error) {
        logger.error(`Erro ao buscar objeto ${id} de ${endpoint}:`, error.response?.data || error.message);
        throw error;
    }
};

/**
 * Cria um novo objeto na API do Django.
 * @param {string} endpoint O endpoint da API (ex: '/crm/accounts/').
 * @param {object} data Os dados para criar o objeto.
 * @returns {Promise<object>} O objeto criado.
 */
const createObject = async (endpoint, data) => {
    try {
        const response = await apiClient.post(endpoint, data);
        logger.info(`Objeto criado com sucesso em ${endpoint}`);
        return response.data;
    } catch (error) {
        logger.error(`Erro ao criar objeto em ${endpoint}:`, error.response?.data || error.message);
        throw error;
    }
};

/**
 * Atualiza um objeto existente na API do Django.
 * @param {string} endpoint O endpoint da API (ex: '/crm/leads/').
 * @param {string} id O ID do objeto a ser atualizado.
 * @param {object} data Os dados para atualizar.
 * @returns {Promise<object>} O objeto atualizado.
 */
const updateObject = async (endpoint, id, data) => {
    try {
        const response = await apiClient.patch(`${endpoint}${id}/`, data);
        logger.info(`Objeto ${id} atualizado com sucesso em ${endpoint}`);
        return response.data;
    } catch (error) {
        logger.error(`Erro ao atualizar objeto ${id} em ${endpoint}:`, error.response?.data || error.message);
        throw error;
    }
};

module.exports = {
    getObject,
    createObject,
    updateObject,
    apiClient // Exporta a instância para buscas mais complexas se necessário
};
