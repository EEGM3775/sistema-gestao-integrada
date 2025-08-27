const { armazenarNF } = require('./armazenarNF');
const { logger, logToDjango } = require('./logger');
const { phpBridge } = require('./phpBridge');

async function consultarNF(nfId, invoiceId, user_id) {
  const acao = 'Consulta de status de NF';
  logger.info(`${acao} para a NF ID: ${nfId} (NFE.io ID: ${invoiceId})`);
  logToDjango(acao, 'funcoesnf', { nfId, invoiceId }, user_id);

  if (!invoiceId) {
    const errorMsg = `O ID da NFE.io (invoiceId) não foi fornecido para a NF ID: ${nfId}.`;
    logger.error(errorMsg);
    logToDjango('Erro de Consulta', 'funcoesnf', { nfId, error: errorMsg }, user_id);
    await armazenarNF(nfId, 'servico', 'ERRO_INTERNO', { error: 'invoiceId não encontrado no sistema.' }, user_id);
    return;
  }

  try {
    const phpResult = await phpBridge.consultarNotaFiscal(invoiceId);

    if (phpResult && phpResult.success) {
      const invoice = phpResult.data;
      logger.info(`Consulta para NFE.io bem-sucedida via PHP. Status atual: ${invoice.status}.`);
      logToDjango('Consulta de NF bem-sucedida', 'funcoesnf', { nfId, invoiceId, status: invoice.status }, user_id);
      const dadosRetorno = { 
        id: invoice.id, 
        status: invoice.status, 
        numero: invoice.number || null, 
        chaveAcesso: invoice.accessKey || null, 
        urlDanfe: invoice.urlPdf || null, 
        urlXml: invoice.urlXml || null, 
        fullResponse: invoice.fullResponse, 
        consultadoVia: 'PHP' 
      };
      await armazenarNF(nfId, 'servico', invoice.status, dadosRetorno, user_id);
    } else {
      const errorMsg = `Erro na consulta PHP para invoice ID ${invoiceId}`;
      logger.error(errorMsg, phpResult.error || 'Resposta inválida do PHP');
      logToDjango('Erro na Consulta via PHP', 'funcoesnf', { nfId, invoiceId, error: phpResult.error }, user_id);
      const errorDetails = { message: 'Erro na comunicação com a API NFE.io via PHP durante a consulta.', details: phpResult.error || 'Resposta inválida' };
      await armazenarNF(nfId, 'servico', 'ERRO', errorDetails, user_id);
    }
  } catch (error) {
    const errorMsg = `Erro inesperado ao tentar consultar a NF ID ${nfId}`;
    logger.error(errorMsg, error.message);
    logToDjango('Erro Crítico na Consulta', 'funcoesnf', { nfId, invoiceId, error: error.message }, user_id);
    const errorDetails = { message: 'Erro inesperado na função de consulta via PHP.', details: error.message };
    await armazenarNF(nfId, 'servico', 'ERRO', errorDetails, user_id);
  }
}

async function baixarPDF(nfId, invoiceId, filename = null, user_id) {
  const acao = 'Download de PDF de NF';
  logger.info(`${acao} para NF ID: ${nfId || 'N/A'} (NFE.io ID: ${invoiceId})`);
  logToDjango(acao, 'funcoesnf', { nfId, invoiceId, filename }, user_id);

  try {
    const phpResult = await phpBridge.baixarPDF(invoiceId, filename);

    if (phpResult && phpResult.success) {
      logger.info(`PDF baixado com sucesso via PHP para NFE.io ID: ${invoiceId}`);
      logToDjango('Download de PDF bem-sucedido', 'funcoesnf', { nfId, invoiceId }, user_id);
      return phpResult;
    } else {
      const errorMsg = `Erro no download PDF via PHP para NFE.io ID ${invoiceId}`;
      logger.error(errorMsg, phpResult.error || 'Erro desconhecido');
      logToDjango('Erro no Download de PDF', 'funcoesnf', { nfId, invoiceId, error: phpResult.error }, user_id);
      return phpResult;
    }
  } catch (error) {
    const errorMsg = `Erro inesperado ao baixar PDF da NFE.io ID ${invoiceId}`;
    logger.error(errorMsg, error.message);
    logToDjango('Erro Crítico no Download de PDF', 'funcoesnf', { nfId, invoiceId, error: error.message }, user_id);
    return { success: false, error: error.message };
  }
}

async function listarNF(filtros = {}, user_id) {
  const acao = 'Listagem de NFs';
  logger.info(`${acao} via PHP com filtros:`, filtros);
  logToDjango(acao, 'funcoesnf', { filtros }, user_id);

  try {
    const phpResult = await phpBridge.listarNotasFiscais(filtros);

    if (phpResult && phpResult.success) {
      logger.info(`Listagem de NFs via PHP concluída com sucesso. Total: ${phpResult.data?.length || 0}`);
      logToDjango('Listagem de NFs bem-sucedida', 'funcoesnf', { count: phpResult.data?.length }, user_id);
      return phpResult;
    } else {
      const errorMsg = 'Erro na listagem de NFs via PHP';
      logger.error(errorMsg, phpResult.error || 'Erro desconhecido');
      logToDjango('Erro na Listagem de NFs', 'funcoesnf', { error: phpResult.error }, user_id);
      return phpResult;
    }
  } catch (error) {
    const errorMsg = 'Erro inesperado ao listar NFs via PHP';
    logger.error(errorMsg, error.message);
    logToDjango('Erro Crítico na Listagem de NFs', 'funcoesnf', { error: error.message }, user_id);
    return { success: false, error: error.message };
  }
}

async function cancelarNF(nfId, invoiceId, reason, user_id) {
  const acao = 'Cancelamento de NF';
  logger.info(`${acao} ID: ${nfId || 'N/A'} (NFE.io ID: ${invoiceId}) - Motivo: ${reason}`);
  logToDjango(acao, 'funcoesnf', { nfId, invoiceId, reason }, user_id);

  try {
    const phpResult = await phpBridge.cancelarNFS(invoiceId, reason);

    if (phpResult && phpResult.success) {
      logger.info(`NF cancelada com sucesso via PHP para NFE.io ID: ${invoiceId}`);
      logToDjango('Cancelamento de NF bem-sucedido', 'funcoesnf', { nfId, invoiceId }, user_id);
      return phpResult;
    } else {
      const errorMsg = `Erro no cancelamento via PHP para NFE.io ID ${invoiceId}`;
      logger.error(errorMsg, phpResult.error || 'Erro desconhecido');
      logToDjango('Erro no Cancelamento de NF', 'funcoesnf', { nfId, invoiceId, error: phpResult.error }, user_id);
      return phpResult;
    }
  } catch (error) {
    const errorMsg = `Erro inesperado ao cancelar NF da NFE.io ID ${invoiceId}`;
    logger.error(errorMsg, error.message);
    logToDjango('Erro Crítico no Cancelamento de NF', 'funcoesnf', { nfId, invoiceId, error: error.message }, user_id);
    return { success: false, error: error.message };
  }
}

module.exports = { 
  consultarNF, 
  baixarPDF, 
  cancelarNF,
  listarNF
};
