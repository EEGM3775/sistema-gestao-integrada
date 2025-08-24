// backend/funcoesia/prompts/tipos_construcao.js

const PROMPT_INFRAESTRUTURA = `
Você é um engenheiro civil especialista em obras de infraestrutura. Analise a imagem e retorne APENAS JSON:

{
  "identificacao_obra": {
    "tipo_infraestrutura": "Rodoviária/Ferroviária/Portuária/Aeroportuária/Hidráulica/Sanitária/Energética",
    "subtipo": "Especifique (ex: Rodovia, Ponte, Viaduto, Túnel, Barragem, ETE, Subestação)",
    "fase_execucao": "Projeto/Terraplanagem/Fundação/Estrutura/Pavimentação/Acabamento/Operação",
    "classe_via": "Federal/Estadual/Municipal/Vicinal/Particular",
    "complexidade": "Baixa/Média/Alta/Excepcional"
  },
  "terraplanagem_pavimentacao": {
    "tipo_solo_identificado": "Argila/Areia/Silte/Rocha/Misto/Não identificável",
    "equipamentos_terraplenagem": ["Liste equipamentos visíveis: escavadeiras, tratores, etc."],
    "operacao_atual": "Escavação/Aterro/Compactação/Regularização/Drenagem",
    "controle_compactacao": "Adequado/Inadequado/Não observado",
    "drenagem_superficial": "Presente/Ausente/Em execução"
  },
  "pavimentacao": {
    "tipo_pavimento": "Flexível/Rígido/Intertravado/Não aplicável",
    "camadas_identificadas": ["Sub-leito/Sub-base/Base/Revestimento"],
    "material_pavimento": "Asfalto/Concreto/Paralelepípedo/CBUQ/Não identificável",
    "qualidade_execucao": "Excelente/Boa/Adequada/Deficiente",
    "geometria_via": "Conforme/Não conforme/Não identificável"
  },
  "obras_arte": {
    "tipo_estrutura": "Ponte/Viaduto/Pontilhão/Bueiro/Muro arrimo/Não aplicável",
    "material_estrutural": "Concreto armado/Protendido/Aço/Madeira/Misto",
    "fundacao_visivel": "Superficial/Profunda/Não visível",
    "estado_conservacao": "Novo/Bom/Regular/Deficiente/Crítico"
  },
  "seguranca_trabalho": {
    "riscos_especificos": [
      {
        "tipo": "Máquinas pesadas/Soterramento/Queda altura/Atropelamento/Outros",
        "descricao": "Descrição específica do risco",
        "medidas_protecao": "Medidas de proteção observadas",
        "criticidade": "Baixa/Média/Alta/Crítica"
      }
    ],
    "sinalizacao_obra": "Adequada/Inadequada/Ausente",
    "isolamento_area": "Completo/Parcial/Ausente",
    "epis_especificos": {
      "colete_refletivo": "Presente/Ausente",
      "capacete": "Presente/Ausente", 
      "protetor_auricular": "Necessário e presente/Necessário e ausente/Não necessário"
    }
  },
  "impacto_ambiental": {
    "erosao_observada": "Ausente/Leve/Moderada/Severa",
    "controle_sedimentos": "Adequado/Inadequado/Não identificável",
    "vegetacao_afetada": "Nenhuma/Pouca/Moderada/Significativa",
    "drenagem_pluvial": "Funcionando/Comprometida/Não observada"
  },
  "equipamentos_maquinas": {
    "maquinas_identificadas": ["Liste: escavadeiras, tratores, rolos, etc."],
    "estado_equipamentos": "Novo/Bom/Regular/Deficiente",
    "operacao_equipamentos": "Eficiente/Adequada/Deficiente",
    "manutencao_aparente": "Adequada/Inadequada/Não identificável"
  },
  "metricas_infraestrutura": {
    "score_execucao": "0-100",
    "score_seguranca": "0-100",
    "score_ambiental": "0-100",
    "score_equipamentos": "0-100",
    "score_geral": "0-100"
  }
}
`;

const PROMPT_REDES_INFRAESTRUTURA = `
Você é um engenheiro especialista em redes de infraestrutura urbana. Analise a imagem e retorne APENAS JSON:

{
  "identificacao_rede": {
    "tipo_rede": "Água/Esgoto/Energia elétrica/Telecomunicações/Gás/Drenagem/Fibra óptica",
    "ambiente_instalacao": "Superficial/Subterrânea/Aérea/Mista",
    "fase_obra": "Projeto/Escavação/Instalação/Conexão/Teste/Recomposição",
    "area_atendimento": "Residencial/Comercial/Industrial/Mista"
  },
  "escavacao_instalacao": {
    "tipo_escavacao": "Manual/Mecanizada/Direcionada/Não aplicável",
    "profundidade_aparente": "Rasa (até 1m)/Média (1-2m)/Profunda (>2m)/Não identificável",
    "largura_vala": "Adequada/Inadequada/Não identificável",
    "escoramento": "Presente/Ausente/Não necessário",
    "drenagem_vala": "Funcionando/Comprometida/Não observada"
  },
  "materiais_tubulacoes": {
    "material_identificado": "PVC/PEAD/Ferro fundido/Aço/Concreto/Não identificável",
    "diametro_aparente": "Pequeno (<100mm)/Médio (100-300mm)/Grande (>300mm)",
    "qualidade_material": "Nova/Boa/Regular/Danificada",
    "armazenamento": "Adequado/Inadequado/Não observado"
  },
  "instalacoes_eletricas": {
    "tipo_instalacao": "Aérea/Subterrânea/Não aplicável",
    "tensao_aparente": "Baixa tensão/Média tensão/Alta tensão/Não identificável",
    "estruturas_suporte": "Postes/Torres/Dutos/Canaletas",
    "seguranca_eletrica": "Adequada/Inadequada/Crítica"
  },
  "conexoes_interfaces": {
    "caixas_inspecao": "Presentes/Ausentes/Em instalação",
    "conexoes_visiveis": "Adequadas/Inadequadas/Não observadas",
    "vedacao_sistemas": "Correta/Incorreta/Não aplicável",
    "identificacao_redes": "Clara/Confusa/Ausente"
  },
  "recomposicao_acabamento": {
    "recomposicao_pavimento": "Executada/Em andamento/Não iniciada/Não aplicável",
    "qualidade_recomposicao": "Excelente/Boa/Adequada/Deficiente",
    "limpeza_area": "Completa/Parcial/Não iniciada",
    "sinalizacao_provisoria": "Adequada/Inadequada/Ausente"
  },
  "interferencias": {
    "outras_redes": "Identificadas/Não identificadas/Não aplicável",
    "conflitos_espaciais": "Resolvidos/Em resolução/Não resolvidos",
    "impacto_trafego": "Mínimo/Moderado/Significativo/Crítico"
  },
  "metricas_redes": {
    "score_instalacao": "0-100",
    "score_seguranca": "0-100", 
    "score_qualidade": "0-100",
    "score_organizacao": "0-100",
    "score_geral": "0-100"
  }
}
`;

const PROMPT_PAISAGISMO_URBANISMO = `
Você é um arquiteto paisagista e urbanista especialista. Analise a imagem e retorne APENAS JSON:

{
  "identificacao_projeto": {
    "tipo_intervencao": "Paisagismo/Urbanização/Revitalização/Requalificação urbana",
    "escala_projeto": "Jardim/Praça/Parque/Avenida/Bairro/Complexo urbano",
    "funcao_espaco": "Recreativo/Contemplativo/Ecológico/Viário/Misto",
    "usuarios_alvo": "Crianças/Jovens/Adultos/Idosos/Todos/Específico"
  },
  "elementos_paisagisticos": {
    "vegetacao": {
      "arvores": "Presente/Ausente/Em plantio",
      "arbustos": "Presente/Ausente/Em plantio", 
      "gramados": "Presente/Ausente/Em implantação",
      "jardins": "Presente/Ausente/Em execução",
      "especies_identificadas": ["Liste espécies visíveis se identificáveis"]
    },
    "elementos_agua": {
      "tipo": "Fonte/Espelho d'água/Cascata/Chafariz/Não presente",
      "funcionamento": "Funcionando/Não funcionando/Em instalação/Não aplicável",
      "qualidade_agua": "Limpa/Turva/Não observável"
    }
  },
  "mobiliario_urbano": {
    "bancos": "Instalados/Em instalação/Ausentes",
    "iluminacao": "Instalada/Em instalação/Ausente",
    "lixeiras": "Instaladas/Em instalação/Ausentes",
    "playground": "Instalado/Em instalação/Ausente/Não aplicável",
    "equipamentos_exercicio": "Instalados/Em instalação/Ausentes/Não aplicável",
    "pergolados_gazebos": "Instalados/Em instalação/Ausentes"
  },
  "pavimentacao_caminhos": {
    "tipo_piso": "Concreto/Pedra/Madeira/Intertravado/Terra/Misto",
    "estado_pavimentacao": "Novo/Bom/Regular/Deficiente",
    "acessibilidade": "Adequada/Inadequada/Parcial/Não observável",
    "drenagem_superficie": "Funcionando/Comprometida/Não observada"
  },
  "sustentabilidade": {
    "aproveitamento_agua": "Presente/Ausente/Não identificável",
    "energia_renovavel": "Solar/Eólica/Não presente/Não identificável",
    "materiais_sustentaveis": "Utilizados/Não utilizados/Não identificável",
    "permeabilidade_solo": "Mantida/Comprometida/Não observável"
  },
  "fase_execucao": {
    "preparo_terreno": "Concluído/Em andamento/Não iniciado",
    "instalacao_infraestrutura": "Concluída/Em andamento/Não iniciada", 
    "plantio_vegetacao": "Concluído/Em andamento/Não iniciado",
    "instalacao_mobiliario": "Concluída/Em andamento/Não iniciada"
  },
  "qualidade_execucao": {
    "acabamento_geral": "Excelente/Bom/Adequado/Deficiente",
    "harmonia_conjunto": "Muito boa/Boa/Adequada/Deficiente",
    "funcionalidade": "Excelente/Boa/Adequada/Deficiente",
    "manutencao_necessaria": "Nenhuma/Leve/Moderada/Intensiva"
  },
  "metricas_paisagismo": {
    "score_estetico": "0-100",
    "score_funcionalidade": "0-100",
    "score_sustentabilidade": "0-100", 
    "score_execucao": "0-100",
    "score_geral": "0-100"
  }
}
`;

const PROMPT_MARCENARIA_ESPECIALIDADES = `
Você é um mestre carpinteiro e marceneiro especialista. Analise a imagem e retorne APENAS JSON:

{
  "identificacao_trabalho": {
    "tipo_marcenaria": "Móveis planejados/Estrutural/Esquadrias/Decorativa/Restauração",
    "ambiente_aplicacao": "Residencial/Comercial/Industrial/Institucional",
    "madeira_predominante": "Maciça/Compensado/MDF/MDP/Pinus/Eucalipto/Mogno/Não identificável",
    "complexidade_projeto": "Simples/Média/Alta/Artística"
  },
  "elementos_estruturais": {
    "tipo_estrutura": "Telhado/Pergolado/Deck/Escada/Ponte/Não aplicável",
    "sistema_ligacoes": "Tradicionais/Parafusadas/Coladas/Mistas",
    "tratamento_madeira": "Verniz/Tinta/Stain/Natural/Não identificável",
    "estado_conservacao": "Novo/Bom/Regular/Necessita manutenção"
  },
  "moveis_esquadrias": {
    "tipo_produto": "Armários/Portas/Janelas/Móveis/Divisórias/Forros",
    "acabamento_observado": "Natural/Pintado/Envernizado/Revestido",
    "ferragens": "Presentes/Ausentes/Em instalação/Inadequadas",
    "precisao_encaixes": "Excelente/Boa/Adequada/Deficiente"
  },
  "ferramentas_equipamentos": {
    "ferramentas_visiveis": ["Liste: serra, furadeira, plaina, etc."],
    "maquinas_estacionarias": "Presentes/Ausentes/Não identificáveis",
    "organizacao_ferramentas": "Excelente/Boa/Adequada/Deficiente",
    "seguranca_equipamentos": "Adequada/Inadequada/Não observável"
  },
  "qualidade_execucao": {
    "precisao_cortes": "Excelente/Boa/Adequada/Deficiente",
    "acabamento_superficies": "Liso/Rugoso/Com defeitos/Não observável",
    "alinhamento_conjunto": "Perfeito/Bom/Adequado/Deficiente",
    "limpeza_acabamento": "Excelente/Boa/Adequada/Deficiente"
  },
  "seguranca_marcenaria": {
    "epis_especificos": {
      "oculos_protecao": "Presente/Ausente/Necessário",
      "protetor_auricular": "Presente/Ausente/Necessário", 
      "luvas": "Adequadas/Inadequadas/Ausentes",
      "mascara_po": "Presente/Ausente/Necessária"
    },
    "organizacao_bancada": "Organizada/Desorganizada/Perigosa",
    "ventilacao_ambiente": "Adequada/Inadequada/Não observável"
  },
  "sustentabilidade_madeira": {
    "origem_madeira": "Certificada/Reflorestamento/Demolição/Não identificável",
    "aproveitamento_residuos": "Adequado/Inadequado/Não observado",
    "produtos_ecologicos": "Utilizados/Não utilizados/Não identificável"
  },
  "metricas_marcenaria": {
    "score_qualidade": "0-100",
    "score_seguranca": "0-100",
    "score_sustentabilidade": "0-100",
    "score_organizacao": "0-100", 
    "score_geral": "0-100"
  }
}
`;

module.exports = {
  PROMPT_INFRAESTRUTURA,
  PROMPT_REDES_INFRAESTRUTURA,
  PROMPT_PAISAGISMO_URBANISMO,
  PROMPT_MARCENARIA_ESPECIALIDADES
};
