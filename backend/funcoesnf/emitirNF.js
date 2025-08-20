const axios = require('axios');
const { DJANGO_API_URL, NFE_IO_API_KEY, NFE_IO_COMPANY_ID } = require('./config');
const { armazenarNF } = require('./armazenarNF');
const logger = require('./logger');
const nfeio = require('nfe-io')(NFE_IO_API_KEY); // Initialize nfe-io library

async function emitirNF(faturaId, nfId, tipoNF) {
  logger.info(`Iniciando emissão de ${tipoNF} para a Fatura ID ${faturaId} e NF ID ${nfId}`);

  let faturaData;
  let clienteData;

  // 1. Buscar os dados completos da fatura no Django
  try {
    const faturaResponse = await axios.get(`${DJANGO_API_URL}/faturas/${faturaId}/`);
    faturaData = faturaResponse.data;
    logger.info('Dados da fatura obtidos com sucesso do Django:', faturaData);

    // Fetch client data if available
    if (faturaData.cliente) {
      const clienteResponse = await axios.get(`${DJANGO_API_URL}/clientes/${faturaData.cliente}/`);
      clienteData = clienteResponse.data;
      logger.info('Dados do cliente obtidos com sucesso do Django:', clienteData);
    } else {
      logger.warn('Fatura não possui cliente associado. Não será possível emitir NFS-e.');
      await armazenarNF(nfId, tipoNF, 'ERRO', { error: 'Fatura sem cliente associado para emissão de NFS-e.' });
      return;
    }

  } catch (error) {
    logger.error(`Erro ao buscar dados da Fatura ID ${faturaId} ou Cliente no Django:`, error.response ? error.response.data : error.message);
    await armazenarNF(nfId, tipoNF, 'ERRO', { error: 'Não foi possível obter os dados da fatura ou cliente no sistema principal.' });
    return;
  }

  // 2. Montar o payload para a API da NFE.io
  let nfeIoPayload;

  if (tipoNF === 'servico') {
    // Assuming fixed values for cityServiceCode and issRate for now
    const cityServiceCode = '10.01'; // Exemplo: Consultoria
    const issRate = 0.05; // Exemplo: 5%

    nfeIoPayload = {
      description: faturaData.descricao,
      cityServiceCode: cityServiceCode,
      issRate: issRate,
      servicesAmount: parseFloat(faturaData.valor),
      borrower: {
        federalTaxNumber: clienteData.cpf_cnpj,
        name: clienteData.nome_completo || clienteData.razao_social,
        email: clienteData.email,
        address: {
          country: 'BRA',
          postalCode: clienteData.cep,
          state: clienteData.estado,
          city: clienteData.cidade,
          street: clienteData.endereco,
          number: clienteData.numero_endereco,
          complement: clienteData.complemento_endereco,
          district: clienteData.bairro,
        },
      },
    };
  } else {
    logger.error('Emissão de NF-e (produto) não implementada com a API NFE.io.');
    await armazenarNF(nfId, tipoNF, 'ERRO', { error: 'Emissão de NF-e (produto) não suportada/implementada.' });
    return;
  }

  logger.info('Payload para NFE.io:', nfeIoPayload);

  // 3. Chamar a API da NFE.io usando a biblioteca
  try {
    const nfeIoResponse = await nfeio.serviceinvoices.create(NFE_IO_COMPANY_ID, nfeIoPayload);
    
    logger.info('Resposta da NFE.io (via biblioteca):', nfeIoResponse);

    const responseData = nfeIoResponse; // The library might return the data directly
    const dadosRetorno = {
      id: responseData.id,
      status: 'PROCESSANDO',
      numero: responseData.number || null,
      chaveAcesso: responseData.accessKey || null,
      urlDanfe: responseData.links?.find(link => link.rel === 'pdf')?.href || null,
      urlXml: responseData.links?.find(link => link.rel === 'xml')?.href || null,
      fullResponse: responseData,
    };
    logger.info('Emissão para NFE.io bem-sucedida. Status: PROCESSANDO.');
    await armazenarNF(nfId, tipoNF, 'PROCESSANDO', dadosRetorno);
  } catch (error) {
    logger.error(`Erro ao chamar a API da NFE.io (via biblioteca):`, error.message);
    // The nfe-io library might wrap errors differently, so we log error.message
    const errorDetails = { message: error.message, fullError: error };
    await armazenarNF(nfId, tipoNF, 'ERRO', { error: 'Falha na comunicação com a NFE.io (via biblioteca).', details: errorDetails });
  }
}

module.exports = { emitirNF };