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
 * Busca uma análise existente por documento ID.
 * @param {number} documentoId - O ID do documento.
 * @returns {Promise<object|null>} - A análise existente ou null se não existir.
 */
async function getAnaliseByDocumento(documentoId) {
  try {
    const response = await apiClient.get(`/ia/analises/?documento=${documentoId}`);
    
    // A API Django retorna array direto para este endpoint
    if (Array.isArray(response.data) && response.data.length > 0) {
      return response.data[0];
    } else if (response.data.results && response.data.results.length > 0) {
      // Fallback caso mude para formato paginado no futuro
      return response.data.results[0];
    }
    
    return null;
  } catch (error) {
    if (error.response?.status === 404) {
      // Análise não encontrada é um caso normal
      logger.info(`Nenhuma análise encontrada para documento ${documentoId}`);
      return null;
    }
    logger.error(`Erro ao buscar análise para documento ${documentoId}:`, error.response?.data || error.message);
    return null;
  }
}

/**
 * Cria uma nova análise de IA no backend Django ou retorna a existente.
 * @param {object} data - Os dados para criar a análise (documento, status).
 * @returns {Promise<object>} - A resposta da API com os dados da análise criada ou existente.
 */
async function createAnaliseIA(data) {
  try {
    const response = await apiClient.post('/ia/analises/', data);
    return response.data;
  } catch (error) {
    // Se o erro é de duplicação, busca a análise existente
    if (error.response?.status === 400 && 
        error.response?.data?.documento?.includes('já existe')) {
      logger.info(`Análise já existe para documento ${data.documento}, buscando análise existente...`);
      const existingAnalise = await getAnaliseByDocumento(data.documento);
      if (existingAnalise) {
        return existingAnalise;
      }
    }
    
    logger.error('Erro ao criar análise de IA na API Django:', error.response?.data || error.message);
    throw error;
  }
}

/**
 * Cria ou atualiza uma análise para reprocessamento.
 * Se já existir uma análise para o documento, ela será resetada.
 * @param {number} documentoId - O ID do documento.
 * @param {string} tipoAnalise - O tipo de análise.
 * @param {string} categoriaAnalise - A categoria da análise.
 * @returns {Promise<object>} - A análise preparada para reprocessamento.
 */
async function prepararAnaliseParaReprocessamento(documentoId, tipoAnalise, categoriaAnalise) {
  try {
    // Primeiro, verifica se já existe uma análise
    const analiseExistente = await getAnaliseByDocumento(documentoId);
    
    if (analiseExistente) {
      logger.info(`Resetando análise existente ${analiseExistente.analise_ia_id} para reprocessamento...`);
      // Reseta a análise existente
      const analiseResetada = await patchAnaliseIA(analiseExistente.analise_ia_id, {
        status: 'pendente',
        tipo_analise: tipoAnalise,
        categoria_analise: categoriaAnalise,
        resultado_analise: null  // Limpa o resultado anterior
      });
      return analiseResetada;
    } else {
      // Cria nova análise se não existir
      logger.info(`Criando nova análise para documento ${documentoId}...`);
      return await createAnaliseIA({
        documento: documentoId,
        status: 'pendente',
        tipo_analise: tipoAnalise,
        categoria_analise: categoriaAnalise
      });
    }
  } catch (error) {
    logger.error(`Erro ao preparar análise para reprocessamento do documento ${documentoId}:`, error.response?.data || error.message);
    throw error;
  }
}

/**
 * Atualiza o status e o resultado da análise no backend Django.
 * @param {number} analiseId - O ID do objeto de análise (analise_ia_id).
 * @param {object} data - Os dados para atualizar (status, resultado_analise).
 * @returns {Promise<object>} - A resposta da API.
 */
async function patchAnaliseIA(analiseId, data) {
  try {
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
  getAnaliseByDocumento,
  prepararAnaliseParaReprocessamento,
};
