// backend/funcoeswhatsapp/services/api/empreendimentoService.js
const djangoApi = require('../apiClient');
const logger = require('../../logger');

/**
 * Busca os empreendimentos associados a um funcionário.
 * @param {number} funcionarioId - O ID do funcionário.
 * @returns {Promise<{empreendimentos: Array|null, error: string|null}>}
 */
const getEmpreendimentosByFuncionario = async (funcionarioId) => {
  try {
    const response = await djangoApi.get(`/empreendimentos/por-funcionario/?funcionario_id=${funcionarioId}`);
    return { empreendimentos: response.data, error: null };
  } catch (error) {
    logger.error(`Erro ao buscar empreendimentos:`, { error: error.response?.data || error.message });
    return { empreendimentos: null, error: "Ocorreu um erro ao buscar os empreendimentos." };
  }
};

module.exports = {
  getEmpreendimentosByFuncionario,
};
