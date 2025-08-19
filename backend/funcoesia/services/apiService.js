// backend/funcoesia/services/apiService.js
const axios = require('axios');
const config = require('../config');
const logger = require('../logger');

const apiClient = axios.create({
  baseURL: config.djangoApiUrl,
  headers: {
    'Authorization': `Token ${config.djangoApiToken}`,
    'Content-Type': 'application/json',
  },
});

/**
 * Busca os dados de um DocumentoDiario no backend Django.
 * @param {number} documentoId - O ID do documento.
 * @returns {Promise<object>} - Os dados do documento.
 */
async function getDocumentoDiario(documentoId) {
  try {
    // Nota: O endpoint exato pode precisar de ajuste.
    const response = await apiClient.get(`/diario/documentos/${documentoId}/`);
    return response.data;
  } catch (error) {
    logger.error(`Erro ao buscar documento ${documentoId} da API Django:`, error.response?.data || error.message);
    throw error;
  }
}

/**
 * Atualiza o status e o resultado da análise no backend Django.
 * @param {number} analiseId - O ID do objeto de análise.
 * @param {object} data - Os dados para atualizar (status, resultado_analise).
 * @returns {Promise<object>} - A resposta da API.
 */
async function patchAnaliseIA(analiseId, data) {
  try {
    // Nota: Este endpoint ainda precisa ser criado no Django.
    const response = await apiClient.patch(`/ia/analises/${analiseId}/`, data);
    return response.data;
  } catch (error) {
    logger.error(`Erro ao atualizar análise ${analiseId} na API Django:`, error.response?.data || error.message);
    throw error;
  }
}

module.exports = {
  getDocumentoDiario,
  createAnaliseIA,
  patchAnaliseIA,
};
