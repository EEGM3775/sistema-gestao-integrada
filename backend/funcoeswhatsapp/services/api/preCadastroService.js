// backend/funcoeswhatsapp/services/api/preCadastroService.js
const djangoApi = require('../apiClient');
const logger = require('../../logger');

/**
 * Cria um novo registro de pré-cadastro na API do Django.
 * @param {object} data - Dados do pré-cadastro.
 * @returns {Promise<{precadastro: object|null, error: string|null}>}
 */
const createPreCadastro = async (data) => {
  try {
    const response = await djangoApi.post('/nucleo/precadastros/', data);
    return { precadastro: response.data, error: null };
  } catch (error) {
    logger.error(`Erro ao criar pré-cadastro:`, { error: error.response ? error.response.data : error.message });
    return { precadastro: null, error: "Ocorreu um erro ao salvar suas informações." };
  }
};

module.exports = {
  createPreCadastro,
};
