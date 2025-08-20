const express = require('express');
const app = express();
const port = 3002;

const logger = require('./logger'); // Importar o logger

// Importar as funções de cada arquivo
const { emitirNF } = require('./emitirNF');
const { armazenarNF } = require('./armazenarNF');
const { consultarNF } = require('./consultarNF');
const { cancelarNF } = require('./cancelarNF');

app.use(express.json());

// Rota para iniciar a emissão de Nota Fiscal de Serviço (NFS-e)
app.post('/api/emitir-nfse', (req, res) => {
  const { fatura_id, nf_id } = req.body;
  logger.info(`Recebida requisição para emitir NFS-e para Fatura ID: ${fatura_id} e NF ID: ${nf_id}`);

  if (!fatura_id || !nf_id) {
    logger.error('Campos fatura_id ou nf_id ausentes na requisição de NFS-e.');
    return res.status(400).json({ error: 'Os campos fatura_id e nf_id são obrigatórios.' });
  }

  // Retorna a resposta imediata para o Django
  res.status(202).json({ message: 'Requisição de emissão de NFS-e recebida. O processamento continuará em segundo plano.' });

  // Inicia o processo de emissão em segundo plano (não bloqueia a resposta)
  emitirNF(fatura_id, nf_id, 'servico');
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

// Outras rotas (a serem implementadas)
// app.get('/api/consultar/:id', consultarNF);
// app.post('/api/cancelar', cancelarNF);

app.listen(port, () => {
  logger.info(`Microserviço de Notas Fiscais rodando na porta ${port}`);
});
