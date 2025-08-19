const axios = require('axios');
const FormData = require('form-data');
const logger = require('../logger');
const config = require('../config');
const { getExtensionFromMimeType } = require('../utils');

const cache = require('./cacheService');

const djangoApi = axios.create({
  baseURL: config.djangoApiUrl,
  headers: { 'Authorization': `Token ${config.djangoApiToken}` }
});

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

    // Tenta encontrar como Funcionário
    let response = await djangoApi.get(`/rh/funcionarios/?telefone=${phone}`);
    if (response.data && response.data.length > 0) {
      const funcionario = response.data[0];
      if (!funcionario.usuario) {
        identityData = { user: null, role: null, error: `O funcionário '${funcionario.nome_completo}' não possui um usuário de sistema associado.` };
      } else {
        identityData = { user: funcionario, role: 'funcionario', error: null };
      }
    }
    // Tenta encontrar como Cliente
    else {
      response = await djangoApi.get(`/clientes/?telefone=${phone}`);
      if (response.data && response.data.length > 0) {
        identityData = { user: response.data[0], role: 'cliente', error: null };
      }
      // Tenta encontrar como Fornecedor
      else {
        response = await djangoApi.get(`/fornecedores/?telefone=${phone}`);
        if (response.data && response.data.length > 0) {
          identityData = { user: response.data[0], role: 'fornecedor', error: null };
        }
        // Se não encontrar em nenhuma tabela
        else {
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
 * Cria ou atualiza o diário de obra para o dia atual.
 * @param {{obraId: number, descricao: string, usuarioId: number}} diarioData
 * @returns {Promise<{diario: object|null, error: string|null}>}
 */
const createOrUpdateDiario = async (diarioData) => {
  try {
    const payload = {
      obra: diarioData.obraId,
      descricao: diarioData.descricao,
      usuario: diarioData.usuarioId,
    };
    const response = await djangoApi.post('/diario/diarios/', payload);
    return { diario: response.data, error: null };
  } catch (error) {
    logger.error(`Erro ao salvar diário de obra:`, { error: error.response ? error.response.data : error.message });
    return { diario: null, error: "Ocorreu um erro ao salvar o relatório do diário." };
  }
};

/**
 * Baixa a mídia da URL fornecida pela Meta.
 * @param {string} mediaId
 * @returns {Promise<{fileBuffer: Buffer, mimeType: string}|null>}
 */
const downloadMedia = async (mediaId) => {
  try {
    const url_get = `https://graph.facebook.com/${config.meta.apiVersion}/${mediaId}/`;
    const headers = { "Authorization": `Bearer ${config.meta.accessToken}` };
    const mediaInfoResponse = await axios.get(url_get, { headers });
    const mediaUrl = mediaInfoResponse.data.url;

    if (!mediaUrl) {
      throw new Error("URL de download da mídia não encontrada na resposta da Meta.");
    }

    const downloadResponse = await axios.get(mediaUrl, {
      headers,
      responseType: 'arraybuffer'
    });

    return {
      fileBuffer: downloadResponse.data,
      mimeType: downloadResponse.headers['content-type'],
    };
  } catch (error) {
    logger.error(`Falha ao baixar mídia com ID ${mediaId}:`, { error: error.response ? error.response.data : error.message });
    return null;
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
    const mediaData = await downloadMedia(mediaId);
    if (mediaData) {
        const novoDocumento = await uploadDocumentoDiario({
            diarioId: diarioId,
            ...mediaData,
        });
        return novoDocumento;
    }
    return null;
};

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

/**
 * Busca o diário de obra de hoje para um determinado usuário e obra.
 * @param {number} usuarioId - O ID do usuário do sistema.
 * @param {number} obraId - O ID da obra.
 * @returns {Promise<{diario: object|null, error: string|null}>}
 */
const getTodaysDiario = async (usuarioId, obraId) => {
  try {
    // Este endpoint precisará ser criado no Django
    const response = await djangoApi.get(`/diario/diarios/today/?usuario_id=${usuarioId}&obra_id=${obraId}`);
    return { diario: response.data, error: null };
  } catch (error) {
    if (error.response && error.response.status === 404) {
      return { diario: null, error: null }; // Não é um erro, apenas não há diário
    }
    logger.error(`Erro ao buscar diário de hoje:`, { error: error.response?.data || error.message });
    return { diario: null, error: "Ocorreu um erro ao verificar seus diários recentes." };
  }
};

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

/**
 * Busca as obras ativas de um determinado empreendimento às quais um funcionário pertence.
 * @param {number} empreendimentoId - O ID do empreendimento.
 * @param {number} funcionarioId - O ID do funcionário.
 * @returns {Promise<{obras: Array|null, error: string|null}>}
 */
const getObrasByEmpreendimento = async (empreendimentoId, funcionarioId) => {
  try {
    const response = await djangoApi.get(`/obras/obras/?empreendimento_id=${empreendimentoId}&membro_id=${funcionarioId}&status_obra=em_andamento`);
    return { obras: response.data, error: null };
  } catch (error) {
    logger.error(`Erro ao buscar obras do empreendimento ${empreendimentoId}:`, { error: error.response?.data || error.message });
    return { obras: null, error: "Ocorreu um erro ao buscar as obras deste empreendimento." };
  }
};

module.exports = {
  identifyUser,
  getTodaysDiario,
  getEmpreendimentosByFuncionario,
  getObrasByEmpreendimento,
  getObrasByName,
  getObraById,
  createObra,
  createOrUpdateDiario,
  downloadAndUploadMedia,
  createPreCadastro,
};
