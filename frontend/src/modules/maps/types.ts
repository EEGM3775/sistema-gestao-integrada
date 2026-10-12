/** Contratos do Maps — espelham `backend/modulomaps/serializers.py`. */

export type Precisao = 'exata' | 'endereco' | 'cep' | 'municipio' | 'desconhecida'

export interface Ponto { lon: number; lat: number }

/** Um lado do lote: quanto mede e com quem divide. */
export interface Confrontacao {
  lado: 'frente' | 'fundo' | 'lateral_direita' | 'lateral_esquerda'
  rotulo: string
  /** Metros lineares. `null` = lado não medido — não é zero. */
  medida: string | null
  confrontante: string
}

/**
 * O que o mapa precisa saber de uma unidade imobiliária.
 *
 * Área não descreve terreno: o que o contrato, a matrícula e o vizinho
 * reconhecem é quanto mede cada lado e com quem cada lado divide — e o lado da
 * frente é a rua, que é de onde sai o endereço.
 */
export interface UnidadeDetalhe {
  unidade_id: number
  rotulo: string
  empreendimento: string
  tipo: string
  situacao: string
  situacao_rotulo: string
  area_privativa: string | null
  area_total: string | null
  endereco: string
  /** O confrontante da frente — na prática, a rua. */
  rua: string
  confrontacoes: Confrontacao[]
  /** O memorial em uma frase, montado no backend (fonte única). */
  memorial: string
  /**
   * A rua da frente bate com o endereço?
   *
   * `null` = **não dá para dizer** (falta o confrontante ou falta o endereço),
   * e esse é o valor que mais importa: cadastro incompleto não é cadastro
   * errado, e acusar divergência onde só falta dado ensina a ignorar o aviso.
   */
  rua_confere: boolean | null
}

export interface LocalResumo {
  local_id: number
  nome: string
  tipo: string
  ponto: Ponto | null
  precisao: Precisao
  precisao_rotulo: string
  fonte: string
  cidade: string
  uf: string
  vinculo_rotulo: string
  distancia_km: number | null
  /** `null` fora de `tipo: 'unidade'`. */
  unidade_detalhe: UnidadeDetalhe | null
}

export interface Local extends LocalResumo {
  cep: string
  logradouro: string
  numero: string
  bairro: string
  ibge: string
  endereco_completo: string
  fonte_rotulo: string
  area: GeoJSON.Polygon | null
  geocodificado_em: string | null
  observacao: string
  ativo: boolean
}

export interface ItemDaFila {
  tipo:
    | 'sem_coordenada'
    | 'precisao_grosseira'
    | 'rua_divergente'
    | 'ortofoto_vencida'
    | 'voo_sem_autorizacao'
  alvo: string
  quantidade: number
  titulo: string
  acao: string
}

export interface MapaDaEmpresa {
  locais: LocalResumo[]
  resumo: {
    total: number
    com_coordenada: number
    por_tipo: Record<string, number>
    por_precisao: Record<string, number>
  }
  requer_decisao: ItemDaFila[]
  camadas_contratadas: boolean
}

export interface Camada {
  camada_id: number
  nome: string
  descricao: string
  cor: string
  ordem: number
  visivel: boolean
  obra: number | null
  total_feicoes?: number
}

export interface Feicao {
  feicao_id: number
  camada: number
  camada_nome: string
  camada_cor: string
  nome: string
  tipo: string
  geom: GeoJSON.Geometry
  obra: number | null
  data_referencia: string
  grupo: string
  propriedades: Record<string, unknown>
}

export interface Ortofoto {
  ortofoto_id: number
  titulo: string
  chunk_uuid: string
  bbox: GeoJSON.Polygon
  data_voo: string
  gsd_cm: string | null
  url_cog: string
  obra: number | null
  obra_nome: string | null
  dias_desde_voo: number
}

export interface PlanoVoo {
  plano_id: number
  nome: string
  tipo: string
  tipo_rotulo: string
  area: GeoJSON.Polygon
  obra: number | null
  obra_nome: string | null
  gsd_alvo_cm: string
  altura_m: string | null
  sobreposicao_frontal_pct: number
  sobreposicao_lateral_pct: number
  velocidade_ms: string
  angulo_graus: number
  camera_nome: string
  linha: GeoJSON.LineString | null
  waypoints: Array<{ ordem: number; lon: number; lat: number; altura_m: number; heading: number }>
  distancia_m: string | null
  duracao_min: string | null
  fotos_estimadas: number | null
  calculado_em: string | null
  autorizacao_protocolo: string
  autorizacao_validade: string | null
}

export interface MemoriaDoVoo {
  altura_m: number
  espacamento_m: number
  intervalo_foto_m: number
  waypoints: number
}

export interface ParadaRota {
  parada_id: number
  rota: number
  local: number
  local_nome: string
  local_ponto: Ponto | null
  ordem: number
  janela_inicio: string | null
  janela_fim: string | null
  carga_kg: string | null
  chegada_estimada_s: number | null
  observacao: string
}

export interface Rota {
  rota_id: number
  nome: string
  origem: number
  origem_nome: string
  obra: number | null
  data_planejada: string | null
  status: string
  linha: GeoJSON.LineString | null
  distancia_m: string | null
  distancia_km: number | null
  duracao_s: number | null
  procedencia: string
  procedencia_rotulo: string
  paradas: ParadaRota[]
}

export interface ViolacaoDeJanela {
  parada: number
  local: number
  chegada: string
  motivo: string
}

export interface Geofence {
  geofence_id: number
  nome: string
  tipo: string
  local: number
  local_nome: string
  area: GeoJSON.Polygon
  raio_m: number | null
  ativo: boolean
}

export interface CandidatoEndereco {
  cep: string
  logradouro: string
  numero: string
  bairro: string
  cidade: string
  uf: string
  ibge: string
  trecho?: string
  nome?: string
  documento?: string
  confianca: 'alta' | 'media' | 'baixa'
  metodo: string
}

export interface StatusMaps {
  modulo: string
  status: string
  provedores: {
    geocodificacao_endereco: boolean
    motor_rota: boolean
    tiles_raster: boolean
  }
  /** Provedores ligados no servidor PÚBLICO do OSM — funcionam, mas são de teste. */
  provedores_publicos?: Array<'geocodificacao_endereco' | 'motor_rota'>
}

export interface Paginado<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

/* ─── Navegação entre as abas ────────────────────────────────────────────────
 *
 * Mora em `types.ts` e não na página porque quem a **usa** são as abas, e a
 * página é quem as importa: declarar o tipo lá criaria um par de arquivos
 * apontando um para o outro só para dizer o que é um destino.
 */
export type TabMaps = 'mapa' | 'vizinhanca' | 'voos' | 'acervo' | 'rotas'

/** Para onde um item da fila de decisão (ou uma linha da tabela) leva. */
export interface Destino {
  tab: TabMaps
  /** Isola na aba de destino exatamente o que a pendência conta. */
  filtro?: Record<string, string>
  /** Coordenada a enquadrar ao chegar — o "me mostra onde isto está". */
  foco?: { lon: number; lat: number }
  /** Sobe a cada pedido, para o mesmo destino ser reabrível. */
  selo?: number
}

export type Ir = (destino: Destino) => void
