// backend/funcoeswhatsapp/services/api/authService.js
const djangoApi = require('../apiClient');
const logger = require('../../logger');
const cache = require('../cacheService');

/**
 * Identifica o tipo e os dados de um usuário (funcionário, cliente ou fornecedor)
 * com base no número de telefone, utilizando um cache de curta duração.
 * @param {string} phone - O número de telefone no formato E.164 (ex: +5511999999999).
 * @returns {Promise<{user: object, role: string} | {error: string}>}
 */
async function identifyUser(phone) {
  const cacheKey = `identity:${phone}`;
  const IDENTITY_CACHE_TTL = 15; // Cache de 15 segundos

  try {
    // 1. Tenta buscar a identidade do cache
    const cachedIdentity = await cache.get(cacheKey);
    if (cachedIdentity) {
      logger.debug(`Cache HIT para identidade de ${phone}.`);
      return cachedIdentity;
    }

    logger.debug(`Cache MISS para identidade de ${phone}. Buscando na API.`);

    // 2. Se não estiver no cache, busca na API do Django
    let identityData = {};

    // Codifica o telefone para uso na URL
    const encodedPhone = encodeURIComponent(phone);
    logger.debug(`Buscando usuário com telefone: ${phone}`);

    // Tenta encontrar como Funcionário
    let response = await djangoApi.get(`/funcionarios/?telefone=${encodedPhone}`);
    
    if (response.data && response.data.length > 0) {
      const funcionario = response.data[0];
      if (!funcionario.usuario) {
        identityData = { user: null, role: null, error: `O funcionário '${funcionario.nome_completo}' não possui um usuário de sistema associado.` };
      } else {
        // Busca os dados do cargo se o funcionário tiver um
        if (funcionario.cargo) {
          try {
            const cargoResponse = await djangoApi.get(`/cargos/${funcionario.cargo}/`);
            funcionario.cargo = cargoResponse.data; // Substitui o ID pelo objeto completo
          } catch (cargoError) {
            logger.warn(`Erro ao buscar dados do cargo ${funcionario.cargo}:`, cargoError.message);
          }
        }
        identityData = { user: funcionario, role: 'funcionario', error: null };
      }
    }
    // Tenta encontrar como Cliente
    else {
      response = await djangoApi.get(`/clientes/?telefone=${encodedPhone}`);
      if (response.data && response.data.length > 0) {
        identityData = { user: response.data[0], role: 'cliente', error: null };
      }
      // Tenta encontrar como Fornecedor
      else {
        response = await djangoApi.get(`/fornecedores/?telefone=${encodedPhone}`);
        if (response.data && response.data.length > 0) {
          identityData = { user: response.data[0], role: 'fornecedor', error: null };
        }
        // Se não encontrar em nenhuma tabela
        else {
          logger.debug(`Usuário não encontrado para o telefone: ${phone}`);
          identityData = { user: null, role: 'unknown', error: null };
        }
      }
    }
    
    // 3. Salva o resultado no cache antes de retornar
    if (!identityData.error) {
      await cache.set(cacheKey, identityData, IDENTITY_CACHE_TTL);
    }

    return identityData;

  } catch (error) {
    logger.error(`Erro ao identificar usuário para o telefone ${phone}:`, error.response?.data || error.message);
    return { user: null, role: null, error: "Ocorreu um erro ao verificar suas credenciais. Por favor, tente novamente mais tarde." };
  }
}

module.exports = {
  identifyUser,
};
