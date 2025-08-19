// backend/funcoesia/controllers/analiseController.js
const apiService = require('../services/apiService');
const iaService = require('../services/iaService');
const logger = require('../logger');
const axios = require('axios');
const fs = require('fs');
const path = require('path');

// Carrega dinamicamente todos os prompts disponíveis
const prompts = {};
const promptsDir = path.join(__dirname, '../prompts');
fs.readdirSync(promptsDir).forEach(file => {
  if (file.endsWith('.js')) {
    const promptName = path.basename(file, '.js');
    prompts[promptName] = require(path.join(promptsDir, file));
  }
});

/**
 * Orquestra o processo completo de análise de imagem.
 */
async function iniciarAnalise(req, res) {
  const { documento_id, tipo_analise } = req.body;

  if (!documento_id || !tipo_analise) {
    return res.status(400).json({ error: 'Os campos "documento_id" e "tipo_analise" são obrigatórios.' });
  }

  // Valida se o tipo de análise solicitado existe
  const promptSelecionado = prompts[tipo_analise];
  if (!promptSelecionado) {
    logger.warn(`Tentativa de análise com tipo inválido: ${tipo_analise}`);
    return res.status(400).json({ error: `Tipo de análise inválido: ${tipo_analise}` });
  }

  // Responde imediatamente à requisição do Django
  res.status(202).json({ message: 'Requisição de análise recebida.', documento_id, tipo_analise });

  let analise;

  try {
    logger.info(`Iniciando análise do tipo "${tipo_analise}" para o documento ${documento_id}...`);
    analise = await apiService.createAnaliseIA({ documento: documento_id, status: 'pendente' });
    const analiseId = analise.analise_ia_id;

    const documento = await apiService.getDocumentoDiario(documento_id);
    if (!documento || !documento.arquivo) {
      throw new Error('URL do arquivo não encontrada nos detalhes do documento.');
    }

    await apiService.patchAnaliseIA(analiseId, { status: 'em_processamento' });

    const response = await axios.get(documento.arquivo, { responseType: 'arraybuffer' });
    const imageBuffer = Buffer.from(response.data, 'binary');
    const mimeType = response.headers['content-type'];

    // Passa o prompt selecionado para o serviço de IA
    const resultadoAnalise = await iaService.analisarImagem(imageBuffer, mimeType, promptSelecionado);

    await apiService.patchAnaliseIA(analiseId, {
      status: 'concluido',
      resultado_analise: resultadoAnalise,
    });

    logger.info(`Análise do tipo "${tipo_analise}" para o documento ${documento_id} concluída com sucesso.`);

  } catch (error) {
    logger.error(`Erro no fluxo de análise para o documento ${documento_id}:`, error);
    if (analise && analise.analise_ia_id) {
      try {
        await apiService.patchAnaliseIA(analise.analise_ia_id, {
          status: 'erro',
          resultado_analise: { erro: error.message },
        });
      } catch (patchError) {
        logger.error(`Falha ao tentar atualizar o status da análise ${analise.analise_ia_id} para "erro":`, patchError);
      }
    }
  }
}

module.exports = {
  iniciarAnalise,
};
