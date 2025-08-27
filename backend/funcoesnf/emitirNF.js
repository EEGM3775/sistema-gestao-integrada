const axios = require('axios');
const { DJANGO_API_URL, DJANGO_API_TOKEN, NFE_IO_API_KEY, NFE_IO_COMPANY_ID } = require('./config');
const { armazenarNF } = require('./armazenarNF');
const { logger, logToDjango } = require('./logger');

// Verificação de segurança para garantir que as credenciais não são placeholders
if (!NFE_IO_API_KEY || NFE_IO_API_KEY === 'SUA_CHAVE_DE_API_AQUI' || !NFE_IO_COMPANY_ID || NFE_IO_COMPANY_ID === 'SEU_ID_DA_EMPRESA_AQUI') {
  const errorMsg = 'Credenciais da NFE.io não configuradas. Verifique o arquivo config.js.';
  logger.error('################################################################');
  logger.error('### ERRO DE CONFIGURAÇÃO:                                    ###');
  logger.error('### A chave de API da NFE.io ou o ID da empresa não foram    ###');
  logger.error('### configurados corretamente no arquivo config.js.         ###');
  logger.error('################################################################');
  logToDjango('Erro Crítico de Configuração', 'funcoesnf', { error: errorMsg });
  throw new Error(errorMsg);
}

const nfeio = require('nfe-io')(NFE_IO_API_KEY);

async function emitirNF(faturaId, nfId, tipoNF, cityServiceCodeFromDjango, user_id) {
  const acao = `Iniciando emissão de ${tipoNF}`;
  logger.info(`${acao} para a Fatura ID ${faturaId} e NF ID ${nfId}`);
  logToDjango(acao, 'funcoesnf', { faturaId, nfId, tipoNF }, user_id);

  const headers = { 'Authorization': `Token ${DJANGO_API_TOKEN}` };
  let faturaData, clienteData;

  try {
    const faturaResponse = await axios.get(`${DJANGO_API_URL}/erp/faturas/${faturaId}/`, { headers });
    faturaData = faturaResponse.data;
    logger.info('Dados da fatura obtidos com sucesso do Django.');

    if (faturaData.cliente) {
      const clienteResponse = await axios.get(`${DJANGO_API_URL}/clientes/${faturaData.cliente}/`, { headers });
      clienteData = clienteResponse.data;
      logger.info('Dados do cliente obtidos com sucesso do Django.');
    } else {
      const errorMsg = 'Fatura sem cliente associado para emissão de NFS-e.';
      logger.warn(errorMsg);
      logToDjango('Erro de Emissão', 'funcoesnf', { faturaId, nfId, error: errorMsg }, user_id);
      await armazenarNF(nfId, tipoNF, 'ERRO', { error: errorMsg }, user_id);
      return;
    }
  } catch (error) {
    const errorMsg = `Erro ao buscar dados da Fatura ID ${faturaId} ou Cliente no Django.`;
    logger.error(errorMsg, error.response ? error.response.data : error.message);
    logToDjango('Erro de Comunicação com Django', 'funcoesnf', { faturaId, nfId, error: errorMsg, details: error.response ? error.response.data : error.message }, user_id);
    await armazenarNF(nfId, tipoNF, 'ERRO', { error: 'Não foi possível obter os dados da fatura ou cliente no sistema principal.' }, user_id);
    return;
  }

  if (tipoNF !== 'servico') {
    const errorMsg = 'Emissão de NF-e (produto) não implementada com a API NFE.io.';
    logger.error(errorMsg);
    logToDjango('Funcionalidade Não Implementada', 'funcoesnf', { faturaId, nfId, tipoNF, error: errorMsg }, user_id);
    await armazenarNF(nfId, tipoNF, 'ERRO', { error: errorMsg }, user_id);
    return;
  }

  if (!clienteData.cpf_cnpj || !clienteData.cep || !clienteData.cidade_ibge) {
    const errorMsg = 'Dados essenciais do cliente estão faltando (CPF/CNPJ, CEP ou código IBGE da cidade).';
    logger.error(errorMsg);
    logToDjango('Erro de Validação de Dados', 'funcoesnf', { faturaId, nfId, clienteId: clienteData.id, error: errorMsg }, user_id);
    await armazenarNF(nfId, tipoNF, 'ERRO', { error: 'Dados insuficientes do cliente para emissão.' }, user_id);
    return;
  }

  const cpfCnpjNumeros = clienteData.cpf_cnpj.replace(/\D/g, '');
  const borrowerType = cpfCnpjNumeros.length > 11 ? 'LegalEntity' : 'NaturalPerson';

  const nfeIoPayload = {
    cityServiceCode: cityServiceCodeFromDjango,
    description: faturaData.descricao,
    servicesAmount: parseFloat(faturaData.valor),
    borrower: {
      type: borrowerType,
      federalTaxNumber: parseInt(cpfCnpjNumeros),
      name: clienteData.nome_completo || clienteData.razao_social,
      email: clienteData.email,
      address: {
        country: 'BRA',
        postalCode: clienteData.cep ? clienteData.cep.replace(/\D/g, '') : '',
        street: clienteData.endereco || '',
        number: clienteData.numero_endereco || 'S/N',
        additionalInformation: clienteData.complemento_endereco || '',
        district: clienteData.bairro || '',
        city: { code: clienteData.cidade_ibge, name: clienteData.cidade || '' },
        state: clienteData.estado ? clienteData.estado.toUpperCase() : ''
      }
    }
  };

  logger.info('Payload final para NFE.io:', { payload: nfeIoPayload });

  try {
    nfeio.serviceInvoices.create(NFE_IO_COMPANY_ID, nfeIoPayload, async function(err, invoice) {
      if (err) {
        const errorMsg = 'Erro recebido da API NFE.io.';
        logger.error(errorMsg, err);
        logToDjango('Erro na API NFE.io', 'funcoesnf', { faturaId, nfId, error: errorMsg, details: err }, user_id);
        await armazenarNF(nfId, tipoNF, 'ERRO', { message: errorMsg, details: err }, user_id);
        return;
      }

      logger.info('Nota fiscal emitida com sucesso! Resposta da NFE.io:', invoice);
      const dadosRetorno = {
        id: invoice.id,
        status: invoice.status || 'PROCESSANDO',
        numero: invoice.number || null,
        chaveAcesso: invoice.accessKey || null,
        urlDanfe: invoice.links?.find(link => link.rel === 'pdf')?.href || null,
        urlXml: invoice.links?.find(link => link.rel === 'xml')?.href || null,
        fullResponse: invoice,
      };

      const successMsg = `Emissão para NFE.io bem-sucedida. Status: ${invoice.status || 'PROCESSANDO'}`;
      logger.info(successMsg);
      logToDjango('Emissão de NF Concluída', 'funcoesnf', { faturaId, nfId, invoiceId: invoice.id, status: invoice.status }, user_id);
      await armazenarNF(nfId, tipoNF, invoice.status || 'EMITIDA', dadosRetorno, user_id);
    });
  } catch (error) {
    const errorMsg = 'Erro inesperado na comunicação com a API NFE.io.';
    logger.error(errorMsg, error.message);
    logToDjango('Erro Crítico na API NFE.io', 'funcoesnf', { faturaId, nfId, error: errorMsg, details: error.message }, user_id);
    await armazenarNF(nfId, tipoNF, 'ERRO', { message: errorMsg, details: error.message }, user_id);
  }
}

module.exports = { emitirNF };
