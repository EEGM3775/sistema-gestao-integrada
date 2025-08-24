const axios = require('axios');
const { DJANGO_API_URL, DJANGO_API_TOKEN, NFE_IO_API_KEY, NFE_IO_COMPANY_ID } = require('./config');
const { armazenarNF } = require('./armazenarNF');
const logger = require('./logger');

// Verificação de segurança para garantir que as credenciais não são placeholders
if (!NFE_IO_API_KEY || NFE_IO_API_KEY === 'SUA_CHAVE_DE_API_AQUI' || !NFE_IO_COMPANY_ID || NFE_IO_COMPANY_ID === 'SEU_ID_DA_EMPRESA_AQUI') {
  logger.error('################################################################');
  logger.error('### ERRO DE CONFIGURAÇÃO:                                    ###');
  logger.error('### A chave de API da NFE.io ou o ID da empresa não foram    ###');
  logger.error('### configurados corretamente no arquivo config.js.         ###');
  logger.error('################################################################');
  // Impede a inicialização da biblioteca com credenciais inválidas
  throw new Error('Credenciais da NFE.io não configuradas. Verifique o arquivo config.js.');
}

const nfeio = require('nfe-io')(NFE_IO_API_KEY); // Initialize nfe-io library

async function emitirNF(faturaId, nfId, tipoNF, cityServiceCodeFromDjango) {
  logger.info(`Iniciando emissão de ${tipoNF} para a Fatura ID ${faturaId} e NF ID ${nfId}`);

  const headers = {
    'Authorization': `Token ${DJANGO_API_TOKEN}`
  };

  let faturaData;
  let clienteData;

  // 1. Buscar os dados completos da fatura no Django
  try {
    const faturaResponse = await axios.get(`${DJANGO_API_URL}/erp/faturas/${faturaId}/`, { headers });
    faturaData = faturaResponse.data;
    logger.info('Dados da fatura obtidos com sucesso do Django.');

    if (faturaData.cliente) {
      const clienteResponse = await axios.get(`${DJANGO_API_URL}/clientes/${faturaData.cliente}/`, { headers });
      clienteData = clienteResponse.data;
      logger.info('Dados do cliente obtidos com sucesso do Django.');
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
  if (tipoNF !== 'servico') {
    logger.error('Emissão de NF-e (produto) não implementada com a API NFE.io.');
    await armazenarNF(nfId, tipoNF, 'ERRO', { error: 'Emissão de NF-e (produto) não suportada/implementada.' });
    return;
  }

  // Validações de dados essenciais do cliente
  if (!clienteData.cpf_cnpj || !clienteData.cep || !clienteData.cidade_ibge) {
      logger.error('Dados essenciais do cliente estão faltando (CPF/CNPJ, CEP ou código IBGE da cidade).');
      await armazenarNF(nfId, tipoNF, 'ERRO', { error: 'Dados insuficientes do cliente para emissão.' });
      return;
  }

  // Determina o tipo de pessoa (Física ou Jurídica) pelo tamanho do CPF/CNPJ
  const cpfCnpjNumeros = clienteData.cpf_cnpj.replace(/\D/g, ''); // Remove tudo que não é número
  const borrowerType = cpfCnpjNumeros.length > 11 ? 'LegalEntity' : 'NaturalPerson';

  const nfeIoPayload = {
    cityServiceCode: cityServiceCodeFromDjango, // Usa o argumento
    description: faturaData.descricao,
    servicesAmount: parseFloat(faturaData.valor),
    borrower: {
      type: borrowerType,
      federalTaxNumber: parseInt(cpfCnpjNumeros), // Converte para número inteiro
      name: clienteData.nome_completo || clienteData.razao_social,
      email: clienteData.email,
      address: {
        country: 'BRA',
        postalCode: clienteData.cep ? clienteData.cep.replace(/\D/g, '') : '', // Remove formatação
        street: clienteData.endereco || '',
        number: clienteData.numero_endereco || 'S/N',
        additionalInformation: clienteData.complemento_endereco || '',
        district: clienteData.bairro || '',
        city: {
          code: clienteData.cidade_ibge, // Código IBGE do município
          name: clienteData.cidade || ''
        },
        state: clienteData.estado ? clienteData.estado.toUpperCase() : ''
      }
    }
  };

  logger.info('Payload final para NFE.io:', { payload: nfeIoPayload });

  // 3. Chamar a API da NFE.io usando callback (conforme documentação)
  try {
    logger.info('Chamando API NFE.io com payload:', JSON.stringify(nfeIoPayload, null, 2));
    
    nfeio.serviceInvoices.create(NFE_IO_COMPANY_ID, nfeIoPayload, async function(err, invoice) {
      if (err) {
        logger.error('Erro recebido da API NFE.io:', err);
        
        const errorDetails = {
          message: 'Erro na comunicação com a API NFE.io.',
          details: err
        };
        await armazenarNF(nfId, tipoNF, 'ERRO', errorDetails);
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

      logger.info(`Emissão para NFE.io bem-sucedida. Status: ${invoice.status || 'PROCESSANDO'}.`);
      await armazenarNF(nfId, tipoNF, invoice.status || 'EMITIDA', dadosRetorno);
    });

  } catch (error) {
    logger.error('Erro na chamada da API NFE.io:', error.message);
    const errorDetails = {
      message: 'Erro inesperado na comunicação com a API NFE.io.',
      details: error.message
    };
    await armazenarNF(nfId, tipoNF, 'ERRO', errorDetails);
  }
}

module.exports = { emitirNF };
