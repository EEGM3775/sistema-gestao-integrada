// backend/funcoesia/controllers/analiseController.js
const apiService = require('../services/apiService');
const iaService = require('../services/iaService');
const logger = require('../logger');
const axios = require('axios');
const { 
  obterPrompt, 
  obterConfiguracaoAnalise, 
  validarResultado,
  listarTiposPorCategoria,
  recomendarTiposPorCategoria,
  obterEstatisticasTipos,
  TIPOS_ANALISE 
} = require('../prompts/config_prompts');

/**
 * Lista os tipos de análise disponíveis organizados por categoria
 */
async function listarTiposAnalise(req, res) {
  try {
    const tiposPorCategoria = listarTiposPorCategoria();
    const estatisticas = obterEstatisticasTipos();
    
    res.status(200).json({ 
      tipos_por_categoria: tiposPorCategoria,
      estatisticas,
      total_tipos: Object.keys(TIPOS_ANALISE).length
    });
  } catch (error) {
    logger.error('Erro ao listar tipos de análise:', error);
    res.status(500).json({ error: 'Erro interno do servidor' });
  }
}

/**
 * Recomenda tipos de análise baseado na categoria da obra
 */
async function recomendarTipos(req, res) {
  try {
    const { categoria, fase } = req.query;
    
    let recomendacoes = [];
    if (categoria) {
      recomendacoes = recomendarTiposPorCategoria(categoria);
    }
    
    const tiposRecomendados = recomendacoes.map(id => {
      const config = obterConfiguracaoAnalise(id);
      return config ? {
        id: config.id,
        nome: config.nome,
        descricao: config.descricao,
        categoria: config.categoria
      } : null;
    }).filter(Boolean);

    res.status(200).json({ 
      categoria_solicitada: categoria,
      fase_solicitada: fase,
      tipos_recomendados: tiposRecomendados
    });
  } catch (error) {
    logger.error('Erro ao recomendar tipos:', error);
    res.status(500).json({ error: 'Erro interno do servidor' });
  }
}

/**
 * Orquestra o processo completo de análise de imagem.
 */
async function iniciarAnalise(req, res) {
  const { documento_id, tipo_analise = 'completa', metadados = {} } = req.body;

  if (!documento_id) {
    return res.status(400).json({ error: 'O campo "documento_id" é obrigatório.' });
  }

  let analise;

  try {
    // Valida e obtem a configuração do tipo de análise
    const configAnalise = obterConfiguracaoAnalise(tipo_analise);
    if (!configAnalise) {
      const tiposDisponiveis = Object.keys(TIPOS_ANALISE).map(k => TIPOS_ANALISE[k].id);
      logger.warn(`Tentativa de análise com tipo inválido: ${tipo_analise}`);
      return res.status(400).json({ 
        error: `Tipo de análise inválido: ${tipo_analise}`,
        tipos_disponiveis: tiposDisponiveis
      });
    }

    // Responde imediatamente à requisição do Django
    res.status(202).json({ 
      message: 'Requisição de análise recebida.',
      documento_id,
      tipo_analise: configAnalise.nome,
      categoria: configAnalise.categoria,
      status: 'processando'
    });

    logger.info(`Iniciando análise "${configAnalise.nome}" (${configAnalise.categoria}) para documento ${documento_id}...`);
    
    // Prepara análise para reprocessamento (cria nova ou reseta existente)
    analise = await apiService.prepararAnaliseParaReprocessamento(
      documento_id, 
      tipo_analise,
      configAnalise.categoria
    );
    const analiseId = analise.analise_ia_id;

    // Busca detalhes do documento
    const documento = await apiService.getDocumentoDiario(documento_id);
    if (!documento || !documento.arquivo) {
      throw new Error('URL do arquivo não encontrada nos detalhes do documento.');
    }

    // Atualiza status para processamento
    await apiService.patchAnaliseIA(analiseId, { status: 'em_processamento' });

    // Download da imagem
    const response = await axios.get(documento.arquivo, { responseType: 'arraybuffer' });
    const imageBuffer = Buffer.from(response.data, 'binary');
    const mimeType = response.headers['content-type'];

    // Obtem o prompt específico para o tipo de análise
    const prompt = obterPrompt(tipo_analise);
    
    // Realiza análise com IA
    const resultadoAnalise = await iaService.analisarImagem(imageBuffer, mimeType, prompt);

    // Valida se o resultado contém os campos obrigatórios
    if (!validarResultado(resultadoAnalise, tipo_analise)) {
      logger.warn(`Resultado da análise incompleto para documento ${documento_id}, tipo ${tipo_analise}`);
      await apiService.patchAnaliseIA(analiseId, {
        status: 'erro',
        resultado_analise: { 
          erro: 'Resultado da análise incompleto ou malformado',
          resultado_parcial: resultadoAnalise,
          campos_esperados: configAnalise.campos_obrigatorios
        }
      });
      return;
    }

    // Adiciona metadados ao resultado
    const resultadoCompleto = {
      ...resultadoAnalise,
      metadata: {
        tipo_analise: configAnalise.nome,
        categoria_analise: configAnalise.categoria,
        timestamp: new Date().toISOString(),
        versao_prompt: '3.0',
        documento_id: documento_id,
        metadados_adicionais: metadados
      }
    };

    // Salva resultado final
    await apiService.patchAnaliseIA(analiseId, {
      status: 'concluido',
      resultado_analise: resultadoCompleto,
    });

    logger.info(`Análise "${configAnalise.nome}" (${configAnalise.categoria}) para documento ${documento_id} concluída com sucesso.`);

  } catch (error) {
    logger.error(`Erro no fluxo de análise para documento ${documento_id}:`, error.message);
    
    // Atualiza status de erro se a análise foi criada
    if (analise && analise.analise_ia_id) {
      try {
        await apiService.patchAnaliseIA(analise.analise_ia_id, {
          status: 'erro',
          resultado_analise: { 
            erro: error.message,
            timestamp: new Date().toISOString(),
            stack_trace: error.stack
          },
        });
      } catch (patchError) {
        logger.error(`Falha ao atualizar status de erro para análise ${analise.analise_ia_id}:`, patchError);
      }
    }
  }
}

/**
 * Valida um tipo de análise específico
 */
async function validarTipoAnalise(req, res) {
  try {
    const { tipo } = req.params;
    const config = obterConfiguracaoAnalise(tipo);
    
    if (!config) {
      return res.status(404).json({ 
        error: 'Tipo de análise não encontrado',
        tipo_solicitado: tipo
      });
    }

    res.status(200).json({
      tipo_valido: true,
      configuracao: {
        id: config.id,
        nome: config.nome,
        descricao: config.descricao,
        categoria: config.categoria,
        campos_obrigatorios: config.campos_obrigatorios
      }
    });
  } catch (error) {
    logger.error('Erro ao validar tipo de análise:', error);
    res.status(500).json({ error: 'Erro interno do servidor' });
  }
}

module.exports = {
  iniciarAnalise,
  listarTiposAnalise,
  recomendarTipos,
  validarTipoAnalise
};
