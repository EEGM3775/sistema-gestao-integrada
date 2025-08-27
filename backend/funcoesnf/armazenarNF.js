const axios = require('axios');
const { DJANGO_API_URL, DJANGO_API_TOKEN } = require('./config');
const { logger, logToDjango } = require('./logger');

async function armazenarNF(nfId, tipoNF, status, dadosRetorno, user_id) {
  const callbackUrl = `${DJANGO_API_URL}/erp/atualizar-status-nf/`;
  const acao = 'Atualização de status de NF no Django';

  const headers = { 'Authorization': `Token ${DJANGO_API_TOKEN}` };

  const logDetails = { nf_id: nfId, nf_tipo: tipoNF, status: status, dados_retorno: dadosRetorno };
  logger.info(`Enviando callback para o Django: ${callbackUrl}`);
  logger.info(`Dados: `, logDetails);
  logToDjango(acao, 'funcoesnf', logDetails, user_id);

  try {
    await axios.post(callbackUrl, {
      nf_id: nfId,
      nf_tipo: tipoNF,
      status: status,
      dados_retorno: dadosRetorno
    }, { headers });

    const successMsg = `Status da NF ${nfId} atualizado com sucesso no Django.`;
    logger.info(successMsg);
    logToDjango('Callback para Django bem-sucedido', 'funcoesnf', { nfId, status }, user_id);

  } catch (error) {
    const errorMsg = `Erro ao enviar callback para o Django para a NF ${nfId}`;
    const errorDetails = { 
      message: errorMsg, 
      details: error.response ? error.response.data : error.message 
    };
    logger.error(errorMsg, errorDetails.details);
    logToDjango('Erro no Callback para Django', 'funcoesnf', { nfId, ...errorDetails }, user_id);
  }
}

module.exports = { armazenarNF };
