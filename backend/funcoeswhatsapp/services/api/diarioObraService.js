// backend/funcoeswhatsapp/services/api/diarioObraService.js
const FormData = require('form-data');
const djangoApi = require('../apiClient');
const logger = require('../../logger');
const { getExtensionFromMimeType } = require('../../utils');
const whatsappService = require('../whatsappService');

/**
 * Busca o diário de obra de hoje para um determinado usuário e obra.
 * @param {number} usuarioId - O ID do usuário do sistema.
 * @param {number} obraId - O ID da obra.
 * @returns {Promise<object>} Retorna diretamente os dados da API.
 * @throws {Error} Lança um erro se a chamada à API falhar.
 */
const fetchTodaysDiario = async (usuarioId, obraId) => {
  try {
    const response = await djangoApi.get(`/diario/diarios/today/?usuario_id=${usuarioId}&obra_id=${obraId}`);
    return response.data;
  } catch (error) {
    // Se o erro é 404 (nenhum diário encontrado), retornar uma resposta válida
    if (error.response && error.response.status === 404) {
      return {
        exists: false,
        message: 'Nenhum diário encontrado para hoje'
      };
    }
    
    // Para outros erros, logar e lançar exceção
    logger.error(`Erro ao buscar diário de hoje para obra ${obraId}:`, { error: error.response?.data || error.message });
    throw new Error("Ocorreu um erro ao verificar seus diários recentes.");
  }
};

/**
 * Cria ou atualiza o diário de obra para o dia atual.
 * @param {{obraId: number, descricao: string, usuarioId: number, diarioId?: number}} diarioData
 * @returns {Promise<object>} Retorna diretamente os dados da API.
 * @throws {Error} Lança um erro se a chamada à API falhar.
 */
const createOrUpdateDiario = async (diarioData) => {
  try {
    const today = new Date().toISOString().split('T')[0]; // Formato YYYY-MM-DD
    const payload = {
      obra: diarioData.obraId,
      descricao: diarioData.descricao,
      usuario: diarioData.usuarioId,
      data: today,
    };
    
    let response;
    if (diarioData.diarioId) {
      response = await djangoApi.put(`/diario/diarios/${diarioData.diarioId}/`, payload);
    } else {
      response = await djangoApi.post('/diario/diarios/', payload);
    }
    
    return response.data;
  } catch (error) {
    logger.error(`Erro ao salvar diário de obra:`, { error: error.response ? error.response.data : error.message });
    throw new Error("Ocorreu um erro ao salvar o relatório do diário.");
  }
};

/**
 * Faz o upload de um documento para o diário de obra no Django.
 * @param {{diarioId: number, fileBuffer: Buffer, mimeType: string}} docData
 * @returns {Promise<object|null>} O objeto do documento criado ou null em caso de falha.
 */
const uploadDocumentoDiario = async (docData) => {
  try {
    const form = new FormData();
    form.append('diario_obra', docData.diarioId);
    
    const extension = getExtensionFromMimeType(docData.mimeType);
    form.append('arquivo', docData.fileBuffer, {
      filename: `whatsapp-media.${extension}`,
      contentType: docData.mimeType,
    });

    const response = await djangoApi.post('/diario/documentos/', form, {
      headers: {
        ...form.getHeaders()
      }
    });
    return response.data;
  } catch (error) {
    logger.error(`Erro ao fazer upload do documento para o diário ${docData.diarioId}:`, { error: error.response ? error.response.data : error.message });
    return null;
  }
};

/**
 * Combina o download e o upload de mídia em uma única função.
 * @param {string} mediaId
 * @param {number} diarioId
 * @returns {Promise<object|null>}
 */
const downloadAndUploadMedia = async (mediaId, diarioId) => {
    const mediaData = await whatsappService.downloadMedia(mediaId);
    if (mediaData) {
        const novoDocumento = await uploadDocumentoDiario({
            diarioId: diarioId,
            ...mediaData,
        });
        return novoDocumento;
    }
    return null;
};

module.exports = {
  fetchTodaysDiario,
  createOrUpdateDiario,
  uploadDocumentoDiario,
  downloadAndUploadMedia,
};
