const axios = require('axios');
const { DJANGO_API_URL } = require('./config');
const logger = require('./logger'); // Importar o logger

async function armazenarNF(nfId, tipoNF, status, dadosRetorno) {
  const callbackUrl = `${DJANGO_API_URL}/atualizar-status-nf/`;

  logger.info(`Enviando callback para o Django: ${callbackUrl}`);
  logger.info(`Dados: `, { nf_id: nfId, nf_tipo: tipoNF, status: status, dados_retorno: dadosRetorno });

  try {
    await axios.post(callbackUrl, {
      nf_id: nfId,
      nf_tipo: tipoNF, // 'servico' ou 'produto'
      status: status,
      dados_retorno: dadosRetorno
    });
    logger.info(`Status da NF ${nfId} atualizado com sucesso no Django.`);
  } catch (error) {
    logger.error(`Erro ao enviar callback para o Django para a NF ${nfId}:`, error.response ? error.response.data : error.message);
  }
}

module.exports = { armazenarNF };
