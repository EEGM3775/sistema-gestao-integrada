# Sistema de Análise de Imagens de Obra - Documentação Completa

## Visão Geral

O sistema de análise de imagens foi completamente expandido para cobrir todos os tipos de construção e obras de engenharia civil, desde edificações convencionais até projetos de infraestrutura complexa, mineração, saneamento, paisagismo e restauração patrimonial.

## Categorias de Análise Disponíveis

### 🏢 **Geral - Construção Convencional**
- **Análise Completa**: Análise abrangente para construção convencional
- **Análise de Segurança**: Foco em EPIs, riscos e conformidade com NRs
- **Controle de Qualidade**: Avaliação de execução, materiais e conformidade técnica
- **Análise de Produtividade**: Organização, recursos humanos e otimização
- **Análise Estrutural**: Elementos estruturais e patologias

### 🛣️ **Infraestrutura - Obras Viárias e Transporte**
- **Obras de Infraestrutura**: Rodovias, ferrovias, portos, aeroportos
- **Redes de Infraestrutura**: Água, esgoto, energia, telecomunicações, gás

### 💧 **Saneamento - Sistemas de Tratamento**
- **Obras de Saneamento**: ETAs, ETEs, sistemas de abastecimento e esgotamento

### 🌳 **Urbanismo/Paisagismo - Espaços Públicos**
- **Paisagismo e Urbanismo**: Praças, parques, jardins e projetos urbanos

### ⚙️ **Especialidades - Trabalhos Técnicos**
- **Marcenaria e Carpintaria**: Estruturas de madeira, móveis planejados
- **Instalações Industriais**: Fábricas, montagem industrial

### ⛏️ **Mineração - Extração e Terraplenagem**
- **Mineração e Terraplenagem**: Pedreiras, movimentação de terra, mineração

### 🏛️ **Patrimônio - Conservação Histórica**
- **Restauração e Patrimônio**: Conservação de patrimônio histórico

## API Endpoints Expandida

### GET `/api/analise/tipos`
Lista todos os tipos de análise organizados por categoria.

**Headers:**
```
X-Internal-Service-Token: 49s49S49s4F92s98DdvhtS498s4s4S98s4
Content-Type: application/json
```

**Resposta:**
```json
{
  "tipos_por_categoria": {
    "Geral": [
      {
        "id": "completa",
        "nome": "Análise Completa da Obra",
        "descricao": "Análise abrangente para construção convencional"
      }
    ],
    "Infraestrutura": [
      {
        "id": "infraestrutura", 
        "nome": "Obras de Infraestrutura",
        "descricao": "Análise especializada para obras rodoviárias, ferroviárias"
      }
    ]
  },
  "estatisticas": {
    "total_tipos": 11,
    "por_categoria": {
      "Geral": 5,
      "Infraestrutura": 2,
      "Saneamento": 1,
      "Especialidades": 1,
      "Mineração": 1,
      "Patrimônio": 1
    }
  }
}
```

### GET `/api/analise/recomendacoes?categoria={categoria}`
Recomenda tipos de análise baseado na categoria da obra.

**Parâmetros:**
- `categoria`: EDIFICACAO, INFRAESTRUTURA, SANEAMENTO, PAISAGISMO, INDUSTRIAL, ESPECIALIDADES, PATRIMONIO

**Resposta:**
```json
{
  "categoria_solicitada": "INFRAESTRUTURA",
  "tipos_recomendados": [
    {
      "id": "infraestrutura",
      "nome": "Obras de Infraestrutura", 
      "categoria": "Infraestrutura"
    }
  ]
}
```

### GET `/api/analise/tipos/{tipo}/validar`
Valida um tipo específico de análise.

**Resposta:**
```json
{
  "tipo_valido": true,
  "configuracao": {
    "id": "infraestrutura",
    "nome": "Obras de Infraestrutura",
    "categoria": "Infraestrutura",
    "campos_obrigatorios": ["identificacao_obra", "terraplanagem_pavimentacao"]
  }
}
```

### POST `/api/analise`
Inicia análise de imagem (expandido).

**Payload:**
```json
{
  "documento_id": 123,
  "tipo_analise": "infraestrutura",
  "metadados": {
    "categoria_obra": "rodoviaria",
    "fase": "pavimentacao"
  }
}
```

## Estruturas de Resultado por Tipo

### 🛣️ Obras de Infraestrutura
```json
{
  "identificacao_obra": {
    "tipo_infraestrutura": "Rodoviária",
    "subtipo": "Rodovia federal",
    "fase_execucao": "Pavimentação",
    "classe_via": "Federal",
    "complexidade": "Alta"
  },
  "terraplanagem_pavimentacao": {
    "tipo_solo_identificado": "Argila",
    "equipamentos_terraplenagem": ["Motoniveladora", "Rolo compactador"],
    "operacao_atual": "Compactação",
    "controle_compactacao": "Adequado"
  },
  "pavimentacao": {
    "tipo_pavimento": "Flexível",
    "material_pavimento": "CBUQ",
    "qualidade_execucao": "Boa"
  },
  "metricas_infraestrutura": {
    "score_execucao": 85,
    "score_seguranca": 80,
    "score_ambiental": 75,
    "score_geral": 80
  }
}
```

### 💧 Obras de Saneamento
```json
{
  "identificacao_obra": {
    "tipo_sistema": "Esgotamento sanitário",
    "componente": "ETE",
    "capacidade_sistema": "Grande porte",
    "fase_construcao": "Instalação equipamentos"
  },
  "estruturas_concreto": {
    "tipo_estrutura": "Decantador",
    "impermeabilizacao": "Aplicada",
    "acabamento_interno": "Liso"
  },
  "equipamentos_mecanicos": {
    "bombas": "Instaladas",
    "aeradores": "Em instalação",
    "estado_equipamentos": "Novo"
  },
  "metricas_saneamento": {
    "score_construcao": 90,
    "score_equipamentos": 85,
    "score_ambiental": 80,
    "score_geral": 85
  }
}
```

### 🌳 Paisagismo e Urbanismo
```json
{
  "identificacao_projeto": {
    "tipo_intervencao": "Paisagismo",
    "escala_projeto": "Parque",
    "funcao_espaco": "Recreativo",
    "usuarios_alvo": "Todos"
  },
  "elementos_paisagisticos": {
    "vegetacao": {
      "arvores": "Presente",
      "gramados": "Em implantação",
      "especies_identificadas": ["Pau-brasil", "Ipê amarelo"]
    },
    "elementos_agua": {
      "tipo": "Fonte",
      "funcionamento": "Funcionando"
    }
  },
  "mobiliario_urbano": {
    "bancos": "Instalados",
    "iluminacao": "Instalada",
    "playground": "Instalado"
  },
  "metricas_paisagismo": {
    "score_estetico": 90,
    "score_funcionalidade": 85,
    "score_sustentabilidade": 80,
    "score_geral": 85
  }
}
```

### ⛏️ Mineração e Terraplenagem
```json
{
  "identificacao_operacao": {
    "tipo_operacao": "Pedreira",
    "metodo_lavra": "Céu aberto",
    "material_extraido": "Rocha",
    "finalidade": "Construção civil"
  },
  "equipamentos_pesados": {
    "maquinas_identificadas": ["Escavadeira", "Caminhão fora de estrada"],
    "porte_equipamentos": "Grande",
    "produtividade_aparente": "Alta"
  },
  "controle_ambiental": {
    "supressao_po": "Adequada",
    "controle_ruido": "Adequado",
    "drenagem_mina": "Funcionando"
  },
  "metricas_mineracao": {
    "score_produtividade": 90,
    "score_seguranca": 75,
    "score_ambiental": 80,
    "score_geral": 82
  }
}
```

### 🏭 Instalações Industriais
```json
{
  "identificacao_instalacao": {
    "tipo_industria": "Automobilística",
    "area_fabrica": "Produção",
    "nivel_automacao": "Automatizada",
    "porte_instalacao": "Grande"
  },
  "estruturas_industriais": {
    "tipo_estrutura": "Galpão",
    "material_estrutural": "Aço",
    "pe_direito": "Alto"
  },
  "equipamentos_processos": {
    "maquinas_visiveis": ["Linha de montagem", "Robôs industriais"],
    "linhas_producao": "Instaladas"
  },
  "metricas_industrial": {
    "score_infraestrutura": 95,
    "score_seguranca": 90,
    "score_ambiental": 85,
    "score_geral": 90
  }
}
```

### 🪵 Marcenaria e Carpintaria
```json
{
  "identificacao_trabalho": {
    "tipo_marcenaria": "Estrutural",
    "ambiente_aplicacao": "Residencial",
    "madeira_predominante": "Eucalipto",
    "complexidade_projeto": "Alta"
  },
  "elementos_estruturais": {
    "tipo_estrutura": "Telhado",
    "sistema_ligacoes": "Tradicionais",
    "tratamento_madeira": "Verniz"
  },
  "qualidade_execucao": {
    "precisao_cortes": "Excelente",
    "acabamento_superficies": "Liso",
    "alinhamento_conjunto": "Perfeito"
  },
  "metricas_marcenaria": {
    "score_qualidade": 95,
    "score_seguranca": 85,
    "score_sustentabilidade": 80,
    "score_geral": 87
  }
}
```

### 🏛️ Restauração e Patrimônio
```json
{
  "identificacao_patrimonio": {
    "tipo_edificacao": "Religioso",
    "periodo_historico": "Colonial",
    "sistema_construtivo": "Alvenaria",
    "valor_patrimonial": "Nacional"
  },
  "estado_conservacao": {
    "estrutura_geral": "Regular",
    "cobertura": "Parcial",
    "paredes": "Fissuras"
  },
  "intervencoes_restauro": {
    "tipo_intervencao": "Restauro",
    "criterios_seguidos": "Carta de Veneza",
    "reversibilidade": "Garantida"
  },
  "metricas_restauracao": {
    "score_conservacao": 70,
    "score_autenticidade": 90,
    "score_tecnico": 85,
    "score_geral": 82
  }
}
```

## Configurações por Categoria de Obra

### Edificação Convencional
- **Tipos recomendados**: completa, estrutural, qualidade, seguranca
- **Fases típicas**: Fundação → Estrutura → Vedação → Instalações → Acabamento

### Infraestrutura Viária
- **Tipos recomendados**: infraestrutura, seguranca, mineracao
- **Fases típicas**: Projeto → Terraplenagem → Drenagem → Pavimentação → Sinalização

### Saneamento
- **Tipos recomendados**: saneamento, seguranca, estrutural
- **Fases típicas**: Escavação → Estrutura → Equipamentos → Teste → Operação

### Paisagismo
- **Tipos recomendados**: paisagismo, qualidade
- **Fases típicas**: Preparo → Infraestrutura → Plantio → Mobiliário → Acabamento

### Industrial
- **Tipos recomendados**: industrial, seguranca, estrutural
- **Fases típicas**: Fundação → Estrutura → Equipamentos → Utilidades → Comissionamento

### Especialidades (Marcenaria, etc.)
- **Tipos recomendados**: marcenaria, qualidade, seguranca
- **Fases típicas**: Preparação → Execução → Acabamento → Instalação

### Patrimônio Histórico
- **Tipos recomendados**: restauracao, qualidade, estrutural
- **Fases típicas**: Diagnóstico → Conservação → Restauro → Adequação

## Normas Regulamentadoras por Tipo de Obra

### Construção Civil
- **NR-6**: Equipamento de Proteção Individual
- **NR-18**: Condições na Indústria da Construção
- **NR-35**: Trabalho em Altura

### Obras de Infraestrutura
- **NR-18**: Construção civil
- **NR-22**: Trabalhos subterrâneos (túneis)
- **NR-31**: Trabalho aquaviário (pontes, portos)

### Mineração
- **NR-22**: Mineração
- **NR-6**: EPIs específicos
- **NR-19**: Explosivos

### Instalações Industriais
- **NR-12**: Máquinas e equipamentos
- **NR-10**: Instalações elétricas
- **NR-13**: Vasos de pressão

### Saneamento
- **NR-18**: Construção civil
- **NR-15**: Atividades insalubres
- **NR-33**: Espaços confinados

## Integração com Django Expandida

```python
import requests

headers = {
    'X-Internal-Service-Token': 'seu-token-aqui',
    'Content-Type': 'application/json'
}

# Listar todos os tipos por categoria
response = requests.get(
    'http://localhost:3002/api/analise/tipos',
    headers=headers
)
print(response.json()['tipos_por_categoria'])

# Obter recomendações por categoria
response = requests.get(
    'http://localhost:3002/api/analise/recomendacoes?categoria=INFRAESTRUTURA',
    headers=headers
)

# Iniciar análise específica
payload = {
    'documento_id': 123,
    'tipo_analise': 'infraestrutura',
    'metadados': {
        'categoria_obra': 'rodoviaria',
        'fase': 'pavimentacao',
        'observacoes': 'Rodovia BR-101, km 150'
    }
}

response = requests.post(
    'http://localhost:3002/api/analise',
    json=payload,
    headers=headers
)
```

## Estatísticas do Sistema

- **Total de tipos de análise**: 11
- **Categorias cobertas**: 7
- **Especialidades**: Todas as principais áreas da engenharia civil
- **Normas consideradas**: Mais de 15 NRs aplicáveis
- **Versão dos prompts**: 3.0 (completamente reformulada)

O sistema agora oferece cobertura completa para todos os tipos de obras de engenharia civil, desde pequenos projetos residenciais até grandes obras de infraestrutura, garantindo análises especializadas e precisas para cada contexto específico.
