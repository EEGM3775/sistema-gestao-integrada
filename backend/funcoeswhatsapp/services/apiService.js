const axios = require('axios');
const FormData = require('form-data');
const logger = require('../logger');
const config = require('../config');
const { getExtensionFromMimeType } = require('../utils');

const djangoApi = axios.create({
  baseURL: config.djangoApiUrl, // Corrigido para usar a nova estrutura de config
  headers: { 'Authorization': `Token ${config.djangoApiToken}` } // Corrigido para usar Token
});

/**
 * Identifica o tipo e os dados de um usuário (funcionário, cliente ou fornecedor)
 * com base no número de telefone.
 * @param {string} phone - O número de telefone no formato E.164 (ex: +5511999999999).
 * @returns {Promise<{user: object, role: string} | {error: string}>}
 */
async function identifyUser(phone) {
  try {
    // 1. Tenta encontrar como Funcionário
    let response = await djangoApi.get(`/rh/funcionarios/?telefone=${phone}`);
    if (response.data && response.data.length > 0) {
      logger.info(`Usuário ${phone} identificado como Funcionário.`);
      const funcionario = response.data[0];
      if (!funcionario.usuario) {
         logger.warn(`Funcionário ${funcionario.nome_completo} não possui usuário associado.`);
         return { user: null, role: null, error: `O funcionário '${funcionario.nome_completo}' não possui um usuário de sistema associado.` };
      }
      return { user: funcionario, role: 'funcionario', error: null };
    }

    // 2. Tenta encontrar como Cliente
    response = await djangoApi.get(`/clientes/?telefone=${phone}`);
    if (response.data && response.data.length > 0) {
      logger.info(`Usuário ${phone} identificado como Cliente.`);
      return { user: response.data[0], role: 'cliente', error: null };
    }

    // 3. Tenta encontrar como Fornecedor
    response = await djangoApi.get(`/fornecedores/?telefone=${phone}`);
    if (response.data && response.data.length > 0) {
      logger.info(`Usuário ${phone} identificado como Fornecedor.`);
      return { user: response.data[0], role: 'fornecedor', error: null };
    }

    // 4. Se não encontrar em nenhuma tabela
    logger.warn(`Nenhum usuário encontrado para o telefone ${phone}.`);
    return { user: null, role: null, error: "Desculpe, seu número de telefone não foi encontrado em nosso sistema." };

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

module.exports = {
  identifyUser,
  getObrasByName,
  getObraById,
  createObra,
  createOrUpdateDiario,
  downloadAndUploadMedia,
};
