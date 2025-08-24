const { armazenarNF } = require('./armazenarNF');
const logger = require('./logger');
const { phpBridge } = require('./phpBridge'); // Usar o bridge central

// Funções principais exportadas

/**
 * Consulta o status de uma NF de forma assíncrona.
 */
async function consultarNF(nfId, invoiceId) {
  logger.info(`Iniciando consulta de status para a NF ID: ${nfId} (NFE.io ID: ${invoiceId})`);
  if (!invoiceId) {
    logger.error(`O ID da NFE.io (invoiceId) não foi fornecido para a NF ID: ${nfId}.`);
    await armazenarNF(nfId, 'servico', 'ERRO_INTERNO', { error: 'invoiceId não encontrado no sistema.' });
    return;
  }

  try {
    // Utiliza o phpBridge para a consulta
    const phpResult = await phpBridge.consultarNotaFiscal(invoiceId);

    if (phpResult && phpResult.success) {
      const invoice = phpResult.data;
      logger.info(`Consulta para NFE.io bem-sucedida via PHP. Status atual: ${invoice.status}.`);
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
      await armazenarNF(nfId, 'servico', invoice.status, dadosRetorno);
    } else {
      logger.error(`Erro na consulta PHP para invoice ID ${invoiceId}:`, phpResult.error || 'Resposta inválida do PHP');
      const errorDetails = { message: 'Erro na comunicação com a API NFE.io via PHP durante a consulta.', details: phpResult.error || 'Resposta inválida' };
      await armazenarNF(nfId, 'servico', 'ERRO', errorDetails);
    }
  } catch (error) {
    logger.error(`Erro inesperado ao tentar consultar a NF ID ${nfId}:`, error.message);
    const errorDetails = { message: 'Erro inesperado na função de consulta via PHP.', details: error.message };
    await armazenarNF(nfId, 'servico', 'ERRO', errorDetails);
  }
}

/**
 * Baixa o PDF de uma NF.
 */
async function baixarPDF(nfId, invoiceId, filename = null) {
  logger.info(`Iniciando download de PDF para NF ID: ${nfId || 'N/A'} (NFE.io ID: ${invoiceId})`);
  try {
    // Utiliza o phpBridge para o download
    const phpResult = await phpBridge.baixarPDF(invoiceId, filename);

    if (phpResult && phpResult.success) {
      logger.info(`PDF baixado com sucesso via PHP para NFE.io ID: ${invoiceId}`);
      return phpResult;
    } else {
      logger.error(`Erro no download PDF via PHP para NFE.io ID ${invoiceId}:`, phpResult.error || 'Erro desconhecido');
      return phpResult;
    }
  } catch (error) {
    logger.error(`Erro inesperado ao baixar PDF da NFE.io ID ${invoiceId}:`, error.message);
    return { success: false, error: error.message };
  }
}

/**
 * Lista as NFs da empresa.
 */
async function listarNF(filtros = {}) {
  logger.info('Iniciando listagem de NFs via PHP com filtros:', filtros);
  try {
    // A funcionalidade de listagem deve ser implementada no phpBridge se necessário
    // Por enquanto, vamos assumir que existe um método listarNotasFiscais
    const phpResult = await phpBridge.listarNotasFiscais(filtros);

    if (phpResult && phpResult.success) {
      logger.info(`Listagem de NFs via PHP concluída com sucesso. Total: ${phpResult.data?.length || 0}`);
      return phpResult;
    } else {
      logger.error('Erro na listagem de NFs via PHP:', phpResult.error || 'Erro desconhecido');
      return phpResult;
    }
  } catch (error) {
    logger.error('Erro inesperado ao listar NFs via PHP:', error.message);
    return { success: false, error: error.message };
  }
}

/**
 * Cancela uma NF.
 */
async function cancelarNF(nfId, invoiceId, reason) {
  logger.info(`Iniciando cancelamento de NF ID: ${nfId || 'N/A'} (NFE.io ID: ${invoiceId}) - Motivo: ${reason}`);
  try {
    // Utiliza o phpBridge para o cancelamento
    const phpResult = await phpBridge.cancelarNFS(invoiceId, reason);

    if (phpResult && phpResult.success) {
      logger.info(`NF cancelada com sucesso via PHP para NFE.io ID: ${invoiceId}`);
      return phpResult;
    } else {
      logger.error(`Erro no cancelamento via PHP para NFE.io ID ${invoiceId}:`, phpResult.error || 'Erro desconhecido');
      return phpResult;
    }
  } catch (error) {
    logger.error(`Erro inesperado ao cancelar NF da NFE.io ID ${invoiceId}:`, error.message);
    return { success: false, error: error.message };
  }
}

module.exports = { 
  consultarNF, 
  baixarPDF, 
  cancelarNF,
  listarNF
};
