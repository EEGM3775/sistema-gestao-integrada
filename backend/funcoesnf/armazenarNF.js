const axios = require('axios');
const { DJANGO_API_URL, DJANGO_API_TOKEN } = require('./config');
const logger = require('./logger'); // Importar o logger

async function armazenarNF(nfId, tipoNF, status, dadosRetorno) {
  const callbackUrl = `${DJANGO_API_URL}/erp/atualizar-status-nf/`;

  const headers = {
    'Authorization': `Token ${DJANGO_API_TOKEN}`
  };

  logger.info(`Enviando callback para o Django: ${callbackUrl}`);
  logger.info(`Dados: `, { nf_id: nfId, nf_tipo: tipoNF, status: status, dados_retorno: dadosRetorno });

  try {
    await axios.post(callbackUrl, {
      nf_id: nfId,
      nf_tipo: tipoNF, // 'servico' ou 'produto'
      status: status,
      dados_retorno: dadosRetorno
    }, { headers });
    logger.info(`Status da NF ${nfId} atualizado com sucesso no Django.`);
  } catch (error) {
    logger.error(`Erro ao enviar callback para o Django para a NF ${nfId}:`, error.response ? error.response.data : error.message);
  }
}

module.exports = { armazenarNF };
