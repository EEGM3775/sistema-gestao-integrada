// backend/funcoesia/prompts/config_prompts.js

const PROMPT_ANALISE_OBRA = require('./progresso_obra');
const {
  PROMPT_ANALISE_SEGURANCA,
  PROMPT_ANALISE_QUALIDADE,
  PROMPT_ANALISE_PRODUTIVIDADE,
  PROMPT_ANALISE_ESTRUTURAL
} = require('./prompts_especializados');

const {
  PROMPT_INFRAESTRUTURA,
  PROMPT_REDES_INFRAESTRUTURA,
  PROMPT_PAISAGISMO_URBANISMO,
  PROMPT_MARCENARIA_ESPECIALIDADES
} = require('./tipos_construcao');

const {
  PROMPT_SANEAMENTO,
  PROMPT_MINERACAO_TERRAPLENAGEM,
  PROMPT_INSTALACOES_INDUSTRIAIS,
  PROMPT_RESTAURACAO_PATRIMONIO
} = require('./obras_especiais');

/**
 * Configuração dos diferentes tipos de análise disponíveis
 */
const TIPOS_ANALISE = {
  // ANÁLISES GERAIS
  COMPLETA: {
    id: 'completa',
    nome: 'Análise Completa da Obra',
    descricao: 'Análise abrangente para construção convencional incluindo progresso, segurança, qualidade e produtividade',
    categoria: 'Geral',
    prompt: PROMPT_ANALISE_OBRA,
    campos_obrigatorios: ['identificacao_obra', 'progresso_execucao', 'seguranca_trabalho', 'metricas_quantitativas']
  },
  
  SEGURANCA: {
    id: 'seguranca',
    nome: 'Análise de Segurança do Trabalho',
    descricao: 'Foco exclusivo em aspectos de segurança, EPIs e conformidade com NRs',
    categoria: 'Especializada',
    prompt: PROMPT_ANALISE_SEGURANCA,
    campos_obrigatorios: ['analise_seguranca']
  },
  
  QUALIDADE: {
    id: 'qualidade',
    nome: 'Controle de Qualidade',
    descricao: 'Análise da qualidade de execução, materiais e conformidade técnica',
    categoria: 'Especializada',
    prompt: PROMPT_ANALISE_QUALIDADE,
    campos_obrigatorios: ['controle_qualidade']
  },
  
  PRODUTIVIDADE: {
    id: 'produtividade', 
    nome: 'Análise de Produtividade',
    descricao: 'Avaliação de organização, recursos humanos e otimização do canteiro',
    categoria: 'Especializada',
    prompt: PROMPT_ANALISE_PRODUTIVIDADE,
    campos_obrigatorios: ['analise_produtividade']
  },
  
  ESTRUTURAL: {
    id: 'estrutural',
    nome: 'Análise Estrutural',
    descricao: 'Avaliação de elementos estruturais e identificação de patologias',
    categoria: 'Especializada',
    prompt: PROMPT_ANALISE_ESTRUTURAL,
    campos_obrigatorios: ['analise_estrutural']
  },

  // INFRAESTRUTURA E OBRAS VIÁRIAS
  INFRAESTRUTURA: {
    id: 'infraestrutura',
    nome: 'Obras de Infraestrutura',
    descricao: 'Análise especializada para obras rodoviárias, ferroviárias, portuárias e de grande porte',
    categoria: 'Infraestrutura',
    prompt: PROMPT_INFRAESTRUTURA,
    campos_obrigatorios: ['identificacao_obra', 'terraplanagem_pavimentacao', 'metricas_infraestrutura']
  },

  REDES: {
    id: 'redes',
    nome: 'Redes de Infraestrutura',
    descricao: 'Análise de instalação de redes de água, esgoto, energia, telecomunicações e gás',
    categoria: 'Infraestrutura',
    prompt: PROMPT_REDES_INFRAESTRUTURA,
    campos_obrigatorios: ['identificacao_rede', 'escavacao_instalacao', 'metricas_redes']
  },

  SANEAMENTO: {
    id: 'saneamento',
    nome: 'Obras de Saneamento',
    descricao: 'Análise de ETAs, ETEs, sistemas de abastecimento e esgotamento sanitário',
    categoria: 'Saneamento',
    prompt: PROMPT_SANEAMENTO,
    campos_obrigatorios: ['identificacao_obra', 'estruturas_concreto', 'metricas_saneamento']
  },

  // OBRAS ESPECIAIS
  PAISAGISMO: {
    id: 'paisagismo',
    nome: 'Paisagismo e Urbanismo',
    descricao: 'Análise de projetos paisagísticos, praças, parques e urbanização',
    categoria: 'Urbanism/Paisagismo',
    prompt: PROMPT_PAISAGISMO_URBANISMO,
    campos_obrigatorios: ['identificacao_projeto', 'elementos_paisagisticos', 'metricas_paisagismo']
  },

  MARCENARIA: {
    id: 'marcenaria',
    nome: 'Marcenaria e Carpintaria',
    descricao: 'Análise de trabalhos em madeira, móveis planejados e estruturas de madeira',
    categoria: 'Especialidades',
    prompt: PROMPT_MARCENARIA_ESPECIALIDADES,
    campos_obrigatorios: ['identificacao_trabalho', 'qualidade_execucao', 'metricas_marcenaria']
  },

  MINERACAO: {
    id: 'mineracao',
    nome: 'Mineração e Terraplenagem',
    descricao: 'Análise de operações de mineração, movimentação de terra e pedreiras',
    categoria: 'Mineração',
    prompt: PROMPT_MINERACAO_TERRAPLENAGEM,
    campos_obrigatorios: ['identificacao_operacao', 'equipamentos_pesados', 'metricas_mineracao']
  },

  INDUSTRIAL: {
    id: 'industrial',
    nome: 'Instalações Industriais',
    descricao: 'Análise de construção e montagem de instalações fabris e industriais',
    categoria: 'Industrial',
    prompt: PROMPT_INSTALACOES_INDUSTRIAIS,
    campos_obrigatorios: ['identificacao_instalacao', 'estruturas_industriais', 'metricas_industrial']
  },

  RESTAURACAO: {
    id: 'restauracao',
    nome: 'Restauração e Patrimônio',
    descricao: 'Análise de obras de restauração e conservação do patrimônio histórico',
    categoria: 'Patrimônio',
    prompt: PROMPT_RESTAURACAO_PATRIMONIO,
    campos_obrigatorios: ['identificacao_patrimonio', 'estado_conservacao', 'metricas_restauracao']
  }
};

/**
 * Configurações específicas por categoria de obra
 */
const CONFIGURACOES_POR_CATEGORIA = {
  EDIFICACAO: {
    tipos_recomendados: ['completa', 'estrutural', 'qualidade', 'seguranca'],
    fases_tipicas: ['Fundação', 'Estrutura', 'Vedação', 'Instalações', 'Acabamento']
  },
  
  INFRAESTRUTURA: {
    tipos_recomendados: ['infraestrutura', 'seguranca', 'mineracao'],
    fases_tipicas: ['Projeto', 'Terraplenagem', 'Drenagem', 'Pavimentação', 'Sinalização']
  },
  
  SANEAMENTO: {
    tipos_recomendados: ['saneamento', 'seguranca', 'estrutural'],
    fases_tipicas: ['Escavação', 'Estrutura', 'Equipamentos', 'Teste', 'Operação']
  },

  PAISAGISMO: {
    tipos_recomendados: ['paisagismo', 'qualidade'],
    fases_tipicas: ['Preparo', 'Infraestrutura', 'Plantio', 'Mobiliário', 'Acabamento']
  },

  INDUSTRIAL: {
    tipos_recomendados: ['industrial', 'seguranca', 'estrutural'],
    fases_tipicas: ['Fundação', 'Estrutura', 'Equipamentos', 'Utilidades', 'Comissionamento']
  },

  ESPECIALIDADES: {
    tipos_recomendados: ['marcenaria', 'qualidade', 'seguranca'],
    fases_tipicas: ['Preparação', 'Execução', 'Acabamento', 'Instalação']
  },

  PATRIMONIO: {
    tipos_recomendados: ['restauracao', 'qualidade', 'estrutural'],
    fases_tipicas: ['Diagnóstico', 'Conservação', 'Restauro', 'Adequação']
  }
};

/**
 * Configurações específicas por fase da obra (mantido para compatibilidade)
 */
const CONFIGURACOES_POR_FASE = {
  FUNDACAO: {
    prompts_recomendados: ['completa', 'estrutural', 'seguranca'],
    aspectos_criticos: ['Escavações', 'Armaduras', 'Trabalho em altura em fundações profundas']
  },
  
  ESTRUTURA: {
    prompts_recomendados: ['completa', 'estrutural', 'seguranca', 'qualidade'],
    aspectos_criticos: ['Trabalho em altura', 'Movimentação de cargas', 'Qualidade do concreto']
  },
  
  ALVENARIA: {
    prompts_recomendados: ['completa', 'qualidade', 'produtividade'],
    aspectos_criticos: ['Qualidade da execução', 'Produtividade da equipe', 'Organização']
  },
  
  ACABAMENTO: {
    prompts_recomendados: ['qualidade', 'produtividade', 'seguranca'],
    aspectos_criticos: ['Qualidade dos acabamentos', 'Organização final', 'Limpeza']
  },

  TERRAPLENAGEM: {
    prompts_recomendados: ['infraestrutura', 'mineracao', 'seguranca'],
    aspectos_criticos: ['Estabilidade de taludes', 'Equipamentos pesados', 'Drenagem']
  },

  PAVIMENTACAO: {
    prompts_recomendados: ['infraestrutura', 'qualidade'],
    aspectos_criticos: ['Compactação', 'Geometria da via', 'Drenagem superficial']
  }
};

/**
 * Pesos para cálculo de scores compostos
 */
const PESOS_METRICAS = {
  score_seguranca: {
    epis: 0.30,
    protecoes_coletivas: 0.30,
    riscos_identificados: 0.40
  },
  
  score_qualidade: {
    execucao: 0.50,
    materiais: 0.30,
    conformidade_tecnica: 0.20
  },
  
  score_produtividade: {
    organizacao: 0.40,
    recursos: 0.30,
    logistica: 0.30
  },
  
  score_geral: {
    seguranca: 0.40,
    qualidade: 0.35,
    produtividade: 0.25
  },

  // Pesos específicos por categoria
  score_infraestrutura: {
    execucao: 0.30,
    seguranca: 0.25,
    ambiental: 0.25,
    equipamentos: 0.20
  },

  score_saneamento: {
    construcao: 0.30,
    equipamentos: 0.25,
    ambiental: 0.25,
    operacional: 0.20
  },

  score_paisagismo: {
    estetico: 0.25,
    funcionalidade: 0.25,
    sustentabilidade: 0.25,
    execucao: 0.25
  }
};

/**
 * Obter prompt por tipo de análise
 */
function obterPrompt(tipoAnalise) {
  const tipo = TIPOS_ANALISE[tipoAnalise.toUpperCase()];
  if (!tipo) {
    throw new Error(`Tipo de análise '${tipoAnalise}' não encontrado. Tipos disponíveis: ${Object.keys(TIPOS_ANALISE).join(', ')}`);
  }
  return tipo.prompt;
}

/**
 * Obter configuração completa de um tipo de análise
 */
function obterConfiguracaoAnalise(tipoAnalise) {
  const tipo = TIPOS_ANALISE[tipoAnalise.toUpperCase()];
  if (!tipo) {
    return null;
  }
  return tipo;
}

/**
 * Listar tipos por categoria
 */
function listarTiposPorCategoria() {
  const categorias = {};
  Object.values(TIPOS_ANALISE).forEach(tipo => {
    if (!categorias[tipo.categoria]) {
      categorias[tipo.categoria] = [];
    }
    categorias[tipo.categoria].push({
      id: tipo.id,
      nome: tipo.nome,
      descricao: tipo.descricao
    });
  });
  return categorias;
}

/**
 * Recomendar tipos de análise baseado na categoria da obra
 */
function recomendarTiposPorCategoria(categoria) {
  const config = CONFIGURACOES_POR_CATEGORIA[categoria.toUpperCase()];
  return config ? config.tipos_recomendados : ['completa'];
}

/**
 * Recomendar tipos de análise baseado na fase da obra (mantido para compatibilidade)
 */
function recomendarTiposAnalise(faseObra) {
  const config = CONFIGURACOES_POR_FASE[faseObra.toUpperCase()];
  return config ? config.prompts_recomendados : ['completa'];
}

/**
 * Validar se o resultado JSON contém os campos obrigatórios
 */
function validarResultado(resultado, tipoAnalise) {
  const config = obterConfiguracaoAnalise(tipoAnalise);
  if (!config) return false;
  
  return config.campos_obrigatorios.every(campo => 
    resultado.hasOwnProperty(campo) && resultado[campo] !== null
  );
}

/**
 * Obter estatísticas dos tipos de análise
 */
function obterEstatisticasTipos() {
  const stats = {
    total_tipos: Object.keys(TIPOS_ANALISE).length,
    por_categoria: {}
  };
  
  Object.values(TIPOS_ANALISE).forEach(tipo => {
    if (!stats.por_categoria[tipo.categoria]) {
      stats.por_categoria[tipo.categoria] = 0;
    }
    stats.por_categoria[tipo.categoria]++;
  });
  
  return stats;
}

module.exports = {
  TIPOS_ANALISE,
  CONFIGURACOES_POR_FASE,
  CONFIGURACOES_POR_CATEGORIA,
  PESOS_METRICAS,
  obterPrompt,
  obterConfiguracaoAnalise,
  listarTiposPorCategoria,
  recomendarTiposAnalise,
  recomendarTiposPorCategoria,
  validarResultado,
  obterEstatisticasTipos
};
