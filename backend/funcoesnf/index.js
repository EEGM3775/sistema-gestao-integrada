require('dotenv').config({ path: '/home/eegm/02sistema_gestao_integrada/backend/funcoesnf/.env' });

const express = require('express');
const cors = require('cors');
const app = express();
const port = 3003;

const { logger, logToDjango } = require('./logger'); // Importar o logger

// Importar as funções de cada arquivo
const { emitirNF } = require('./emitirNF');
const { armazenarNF } = require('./armazenarNF');
const { consultarNF, baixarPDF, cancelarNF, listarNF } = require('./consultarNF');

// Configurar CORS para aceitar requisições do frontend
app.use(cors({
  origin: [
    'http://localhost:8000',
    'http://127.0.0.1:8000',
    'http://localhost:3000',
    'http://127.0.0.1:3000'
  ],
  methods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
  allowedHeaders: ['Content-Type', 'Authorization'],
  credentials: true
}));

app.use(express.json());

// Rota para iniciar a emissão de Nota Fiscal de Serviço (NFS-e)
app.post('/api/emitir-nfse', (req, res) => {
  const { fatura_id, nf_id, city_service_code } = req.body;
  logger.info(`Recebida requisição para emitir NFS-e para Fatura ID: ${fatura_id} e NF ID: ${nf_id}`);

  if (!fatura_id || !nf_id || !city_service_code) {
    logger.error('Campos fatura_id, nf_id ou city_service_code ausentes na requisição de NFS-e.');
    return res.status(400).json({ error: 'Os campos fatura_id, nf_id e city_service_code são obrigatórios.' });
  }

  // Retorna a resposta imediata para o Django
  res.status(202).json({ message: 'Requisição de emissão de NFS-e recebida. O processamento continuará em segundo plano.' });

  // Inicia o processo de emissão em segundo plano (não bloqueia a resposta)
  emitirNF(fatura_id, nf_id, 'servico', city_service_code);
});

// Rota para iniciar a emissão de Nota Fiscal de Produto (NF-e)
app.post('/api/emitir-nfe', (req, res) => {
  const { fatura_id, nf_id } = req.body;
  logger.info(`Recebida requisição para emitir NF-e para Fatura ID: ${fatura_id} e NF ID: ${nf_id}`);

  if (!fatura_id || !nf_id) {
    logger.error('Campos fatura_id ou nf_id ausentes na requisição de NF-e.');
    return res.status(400).json({ error: 'Os campos fatura_id e nf_id são obrigatórios.' });
  }

  // Retorna a resposta imediata para o Django
  res.status(202).json({ message: 'Requisição de emissão de NF-e recebida. O processamento continuará em segundo plano.' });

  // Inicia o processo de emissão em segundo plano
  emitirNF(fatura_id, nf_id, 'produto');
});

// Rota para consultar o status de uma NF na NFE.io
app.post('/api/consultar-nf', (req, res) => {
  const { nf_id, invoice_id } = req.body;
  logger.info(`Recebida requisição para consultar status da NF ID: ${nf_id} (NFE.io ID: ${invoice_id})`);

  if (!nf_id || !invoice_id) {
    logger.error('Campos nf_id ou invoice_id ausentes na requisição de consulta.');
    return res.status(400).json({ error: 'Os campos nf_id e invoice_id são obrigatórios.' });
  }

  // Retorna a resposta imediata para o Django
  res.status(202).json({ message: 'Requisição de consulta recebida. O processamento continuará em segundo plano.' });

  // Inicia o processo de consulta em segundo plano
  consultarNF(nf_id, invoice_id);
});

// Rota para baixar PDF de uma NF (via PHP)
app.post('/api/baixar-pdf', async (req, res) => {
  const { nf_id, invoice_id, filename } = req.body;
  logger.info(`Recebida requisição para baixar PDF da NF ID: ${nf_id || 'N/A'} (NFE.io ID: ${invoice_id})`);

  if (!invoice_id) {
    logger.error('Campo invoice_id ausente na requisição de download PDF.');
    return res.status(400).json({ error: 'O campo invoice_id é obrigatório.' });
  }

  try {
    // Executa o download do PDF via PHP (nf_id é opcional)
    const resultado = await baixarPDF(nf_id || null, invoice_id, filename);
    
    if (resultado.success) {
      res.json({ 
        success: true, 
        message: 'PDF baixado com sucesso',
        data: resultado.data 
      });
    } else {
      res.status(500).json({ 
        success: false, 
        error: resultado.error,
        debug_info: resultado.debug_info || null
      });
    }
  } catch (error) {
    logger.error('Erro no endpoint de download PDF:', error);
    res.status(500).json({ 
      success: false, 
      error: 'Erro interno no download do PDF' 
    });
  }
});

// Rota para cancelar uma NF (via PHP)
app.post('/api/cancelar-nf', async (req, res) => {
  const { nf_id, invoice_id, reason } = req.body;
  logger.info(`Recebida requisição para cancelar NF ID: ${nf_id || 'N/A'} (NFE.io ID: ${invoice_id}) - Motivo: ${reason}`);

  if (!invoice_id || !reason) {
    logger.error('Campos invoice_id ou reason ausentes na requisição de cancelamento.');
    return res.status(400).json({ error: 'Os campos invoice_id e reason são obrigatórios.' });
  }

  try {
    // Executa o cancelamento via PHP (nf_id é opcional)
    const resultado = await cancelarNF(nf_id || null, invoice_id, reason);
    
    if (resultado.success) {
      res.json({ 
        success: true, 
        message: 'Nota fiscal cancelada com sucesso',
        data: resultado.data 
      });
    } else {
      res.status(500).json({ 
        success: false, 
        error: resultado.error,
        debug_info: resultado.debug_info || null
      });
    }
  } catch (error) {
    logger.error('Erro no endpoint de cancelamento de NF:', error);
    res.status(500).json({ 
      success: false, 
      error: 'Erro interno no cancelamento da NF' 
    });
  }
});

// Rota para testar se um invoice ID existe (debug)
app.post('/api/verificar-invoice', async (req, res) => {
  const { invoice_id } = req.body;
  logger.info(`Verificando se invoice ID existe: ${invoice_id}`);

  if (!invoice_id) {
    return res.status(400).json({ error: 'O campo invoice_id é obrigatório.' });
  }

  try {
    // Tenta consultar a NF para verificar se existe
    const resultado = await consultarNF(null, invoice_id);
    
    res.json({ 
      success: true, 
      exists: true,
      message: 'Invoice encontrado',
      data: resultado
    });
    
  } catch (error) {
    logger.error('Erro ao verificar invoice:', error);
    res.json({ 
      success: false, 
      exists: false,
      error: error.message 
    });
  }
});

// Rota para listar NFs (via PHP)
app.post('/api/listar-nf', async (req, res) => {
  const filtros = req.body.filtros || {};
  logger.info('Recebida requisição para listar NFs com filtros:', filtros);

  try {
    // Executa a listagem via PHP
    const resultado = await listarNF(filtros);
    
    if (resultado.success) {
      res.json({ 
        success: true, 
        message: 'Listagem realizada com sucesso',
        data: resultado.data 
      });
    } else {
      res.status(500).json({ 
        success: false, 
        error: resultado.error 
      });
    }
  } catch (error) {
    logger.error('Erro no endpoint de listagem de NFs:', error);
    res.status(500).json({ 
      success: false, 
      error: 'Erro interno na listagem de NFs' 
    });
  }
});



app.listen(port, () => {
  logger.info(`Microserviço de Notas Fiscais rodando na porta ${port}`);
  logger.info('Funcionalidades disponíveis:');
  logger.info('- POST /api/emitir-nfse - Emisão de NFS-e');
  logger.info('- POST /api/emitir-nfe - Emisão de NF-e');
  logger.info('- POST /api/consultar-nf - Consulta assíncrona de NF');
  logger.info('- POST /api/baixar-pdf - Download de PDF (via PHP)');
  logger.info('- POST /api/cancelar-nf - Cancelamento de NF (via PHP)');
  logger.info('- POST /api/listar-nf - Listagem de NFs (via PHP)');
});