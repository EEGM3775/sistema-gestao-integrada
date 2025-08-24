// backend/funcoeswhatsapp/services/api/obraService.js
const djangoApi = require('../apiClient');
const logger = require('../../logger');

/**
 * Busca todas as obras.
 * @returns {Promise<Array>} Retorna a lista de obras da API.
 * @throws {Error} Lança um erro se a chamada à API falhar.
 */
const getObras = async () => {
  try {
    const response = await djangoApi.get('/obras/');
    return response.data;
  } catch (error) {
    logger.error('Erro ao buscar obras:', { error: error.response?.data || error.message });
    throw new Error("Ocorreu um erro ao buscar as obras.");
  }
};

/**
 * Busca obras na API do Django pelo nome.
 * @param {string} name 
 * @returns {Promise<{obras: Array|null, error: string|null}>}
 */
const getObrasByName = async (name) => {
  try {
    const response = await djangoApi.get(`/obras/obras/?nome_obra__icontains=${encodeURIComponent(name)}`);
    if (response.data) {
      return { obras: response.data, error: null };
    }
    return { obras: [], error: null };
  } catch (error) {
    logger.error(`Erro ao buscar obras com nome "${name}":`, { message: error.message });
    return { obras: null, error: "Ocorreu um erro ao buscar a obra. Tente novamente mais tarde." };
  }
};

/**
 * Busca uma obra específica pelo seu ID.
 * @param {number} id 
 * @returns {Promise<{obra: object|null, error: string|null}>}
 */
const getObraById = async (id) => {
  try {
    const response = await djangoApi.get(`/obras/obras/${id}/`);
    return { obra: response.data, error: null };
  } catch (error) {
    logger.error(`Erro ao buscar obra com ID "${id}":`, { message: error.message });
    if (error.response && error.response.status === 404) {
      return { obra: null, error: "A obra selecionada não foi encontrada. Por favor, inicie a conversa novamente." };
    }
    return { obra: null, error: "Ocorreu um erro ao buscar os detalhes da obra." };
  }
};

/**
 * Cria uma nova obra na API do Django.
 * @param {{nome: string, endereco: string, responsavelId: number}} obraData 
 * @returns {Promise<{obra: object|null, error: string|null}>}
 */
const createObra = async (obraData) => {
  try {
    const payload = {
      nome_obra: obraData.nome,
      endereco: obraData.endereco,
      responsavel_tecnico: obraData.responsavelId,
    };
    const response = await djangoApi.post('/obras/obras/', payload);
    return { obra: response.data, error: null };
  } catch (error) {
    logger.error(`Erro ao criar obra "${obraData.nome}":`, { error: error.response ? error.response.data : error.message });
    return { obra: null, error: "Ocorreu um erro ao tentar criar a obra. Por favor, tente novamente." };
  }
};

/**
 * Busca as obras ativas de um determinado empreendimento às quais um funcionário pertence.
 * @param {number} empreendimentoId - O ID do empreendimento.
 * @param {number} funcionarioId - O ID do funcionário.
 * @returns {Promise<{obras: Array|null, error: string|null}>}
 */
const getObrasByEmpreendimento = async (empreendimentoId, funcionarioId) => {
  try {
    const response = await djangoApi.get(`/obras/?empreendimento_id=${empreendimentoId}&membro_id=${funcionarioId}&status_obra=em_execucao`);
    return { obras: response.data, error: null };
  } catch (error) {
    logger.error(`Erro ao buscar obras do empreendimento ${empreendimentoId}:`, { error: error.response?.data || error.message });
    return { obras: null, error: "Ocorreu um erro ao buscar as obras deste empreendimento." };
  }
};

module.exports = {
  getObras,
  getObrasByName,
  getObraById,
  createObra,
  getObrasByEmpreendimento,
};
