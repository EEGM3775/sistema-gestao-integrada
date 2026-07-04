// ─── Empreendimentos ──────────────────────────────────────────────────────────

export type StatusEmpreendimento = 'planejamento' | 'em_execucao' | 'concluido' | 'cancelado'

export interface Empreendimento {
  empreendimento_id: number
  empreendimento: string
  razao_social: string
  cnpj: string
  telefone: string
  endereco: string
  data_inicio_prevista: string | null
  data_fim_prevista: string | null
  data_inicio_real: string | null
  data_fim_real: string | null
  orcamento_total: string | null
  status_empreendimento: StatusEmpreendimento
  descricao: string | null
  data_criacao: string
  data_atualizacao: string
  tenant: number
}

export interface ContaBancariaEmpreendimento {
  id: number
  empreendimento: number
  codigo_banco: string
  agencia: string
  agencia_dv: string | null
  conta: string
  conta_dv: string | null
  codigo_cedente: string | null
  carteira: string | null
  codigo_pix: string | null
  tipo_conta: 'corrente' | 'poupanca' | 'investimento'
  numero_agencia: string
  numero_conta: string
  is_principal: 1 | 0
  observacoes: string | null
  data_criacao: string
  data_atualizacao: string
}

export type TipoCusto =
  | 'automovel' | 'equipamentos' | 'extra' | 'fixo' | 'funcionarios'
  | 'imovel' | 'impostos' | 'imprevisto' | 'manutencao' | 'materiais'
  | 'mobiliario' | 'publicidade' | 'seguros' | 'servicos' | 'servicos_terceiros'
  | 'taxas' | 'transporte' | 'variavel' | 'outros'

export interface CustoEmpreendimento {
  custo_id: number
  empreendimento: number | null
  descricao: string | null
  tipo_custo: TipoCusto
  fornecedor: number | null
  produto_servico: number | null
  valor: string
  quantidade: string
  data_custo: string
  valor_total: string
  nota_fiscal: string | null
  data_emissao: string
}

export interface EmpreendimentoFormData {
  empreendimento: string
  razao_social: string
  cnpj: string
  telefone: string
  endereco: string
  data_inicio_prevista: string
  data_fim_prevista: string
  orcamento_total: string
  status_empreendimento: StatusEmpreendimento
  descricao: string
}

export interface ContaBancariaEmpreendimentoFormData {
  empreendimento: number
  tipo_conta: 'corrente' | 'poupanca' | 'investimento'
  codigo_banco: string
  agencia: string
  agencia_dv: string
  conta: string
  conta_dv: string
  codigo_cedente: string
  carteira: string
  codigo_pix: string
  is_principal: 1 | 0
  observacoes: string
}

export interface CustoEmpreendimentoFormData {
  empreendimento: number
  tipo_custo: TipoCusto
  descricao: string
  valor: string
  quantidade: string
  data_custo: string
  nota_fiscal: string
}

// ─── Usuário ──────────────────────────────────────────────────────────────────

export interface User {
  id: number;
  username: string;
  email: string;
}

// ─── Clientes ─────────────────────────────────────────────────────────────────

export type EstadoCivil = 'solteiro' | 'casado' | 'divorciado' | 'viuvo' | 'uniao_estavel'
export type StatusContrato = 'ativo' | 'inativo' | 'cancelado' | 'concluido'
export type CondicoesPagamento = 'a_vista' | 'financiamento_bancario' | 'financiamento_direto' | 'permuta' | 'cartao' | 'outro'

export interface Cliente {
  cliente_id: number
  nome_completo: string
  cpf_cnpj: string
  email: string
  telefone: string
  endereco: string
  numero_endereco: string
  complemento_endereco: string
  bairro: string
  cidade: string
  estado: string
  cep: string
  cidade_ibge: string
  data_nascimento: string
  estado_civil: EstadoCivil | null
  profissao: string | null
  data_cadastro: string
  id_cliente_gateway: string | null
  tenant: number
}

export interface ClienteFormData {
  nome_completo: string
  cpf_cnpj: string
  email: string
  telefone: string
  data_nascimento: string
  estado_civil: EstadoCivil | ''
  profissao: string
  endereco: string
  numero_endereco: string
  complemento_endereco: string
  bairro: string
  cidade: string
  estado: string
  cep: string
}

export interface ClienteEmpreendimento {
  cliente_empreendimento_id: number
  cliente: number
  cliente_nome: string
  empreendimento: number
  empreendimento_nome: string
  unidade_comprada: string
  endereco_unidade: string
  data_compra: string
  valor_compra: string
  condicoes_pagamento: CondicoesPagamento
  observacoes_compra: string | null
  tenant: number
}

export interface ClienteEmpreendimentoFormData {
  cliente: number
  empreendimento: number | ''
  unidade_comprada: string
  endereco_unidade: string
  data_compra: string
  valor_compra: string
  condicoes_pagamento: CondicoesPagamento | ''
  observacoes_compra: string
}

export interface ContratoCliente {
  contrato_cliente_id: number
  cliente: number
  cliente_nome: string
  empreendimento: number
  empreendimento_nome: string
  cliente_empreendimento: number | null
  numero_contrato: string
  data_assinatura: string | null
  objeto_contrato: string
  arquivo_contrato: string | null
  status_contrato: StatusContrato
  responsavel: number | null
  responsavel_nome: string | null
  vendedor: number | null
  vendedor_nome: string | null
  tenant: number
}

export interface ContratoClienteFormData {
  cliente: number
  empreendimento: number | ''
  cliente_empreendimento: number | ''
  numero_contrato: string
  data_assinatura: string
  objeto_contrato: string
  arquivo_contrato: string
  status_contrato: StatusContrato
  responsavel: number | ''
  vendedor: number | ''
}

export interface DocumentoCliente {
  documento_cliente_id: number
  cliente: number
  cliente_nome: string
  tipo_documento: 'rg' | 'cpf' | 'cnh' | 'comprovante_residencia' | 'certidao_casamento' | 'outros'
  tipo_documento_display: string
  nome_documento: string
  arquivo: string
  data_upload: string
  tenant: number
}

export interface DadoBancarioClienteFormData {
  cliente: number
  codigo_banco: string
  agencia: string
  agencia_dv: string
  conta: string
  conta_dv: string
  tipo_conta: 'corrente' | 'poupanca' | 'investimento' | 'salario' | 'outros'
  titular_nome: string
  titular_cpf_cnpj: string
  chave_pix: string
  codigo_cedente: string
  carteira: string
  observacoes: string
}

export interface DadoBancarioCliente {
  id: number
  cliente: number
  cliente_nome: string
  codigo_banco: string
  agencia: string
  agencia_dv: string | null
  conta: string
  conta_dv: string | null
  tipo_conta: 'corrente' | 'poupanca' | 'investimento' | 'salario' | 'outros'
  titular_nome: string
  titular_cpf_cnpj: string
  chave_pix: string | null
  codigo_cedente: string
  carteira: string
  observacoes: string | null
  data_atualizacao: string
  tenant: number
}

// status normalizado da análise de IA (frontend)
export type StatusAnalise = 'sem_analise' | 'pendente' | 'em_andamento' | 'completa' | 'erro'

export type OrigemContribuicao = 'web' | 'whatsapp'

export interface AnaliseIAResumo {
  analise_id: number;
  status: string;
  resultado: unknown;
  data_atualizacao: string;
}

export interface DocumentoDiario {
  documento_diario_id: number;
  diario_obra: number;
  autor: number | null;
  autor_nome: string | null;
  origem: OrigemContribuicao | string;
  arquivo: string;
  descricao: string | null;
  data_criacao: string;
  analise_ia: AnaliseIAResumo | null;
}

export interface EntradaDiario {
  entrada_id: number;
  diario_obra: number;
  autor: number | null;
  autor_nome: string | null;
  origem: OrigemContribuicao | string;
  texto: string;
  eh_ocorrencia: boolean;
  data_criacao: string;
  data_atualizacao: string;
}

// Diário = container do dia (um por obra/data). Conteúdo fica em entradas/documentos.
export interface DiarioObra {
  diario_obra_id: number;
  obra: number;
  obra_nome: string | null;
  data: string;
  descricao: string | null;
  condicoes_climaticas: string | null;
  criado_por: number | null;
  criado_por_nome: string | null;
  pode_moderar: boolean;
  data_criacao: string;
  data_atualizacao: string;
  entradas: EntradaDiario[];
  documentos: DocumentoDiario[];
}

// Payload da ação contribuir (texto e/ou foto, anexado ao diário do dia).
export interface ContribuirData {
  obra: number | null;
  texto: string;
  eh_ocorrencia: boolean;
  condicoes_climaticas: string;
  arquivo: File | null;
}

// ─── Obras ────────────────────────────────────────────────────────────────────

export type StatusObra = 'planejamento' | 'em_execucao' | 'concluida' | 'cancelada'

export interface Obra {
  obra_id: number
  empreendimento: number | null
  nome_obra: string
  endereco: string
  status_obra: StatusObra
  descricao: string | null
  data_inicio_prevista: string | null
  data_fim_prevista: string | null
  data_inicio_real: string | null
  data_fim_real: string | null
  orcamento_previsto: string | null
  data_cadastro: string
  data_atualizacao: string
}

export interface ObraFormData {
  nome_obra: string
  empreendimento: number | null
  endereco: string
  status_obra: StatusObra
  descricao: string
  data_inicio_prevista: string
  data_fim_prevista: string
  orcamento_previsto: string
}

export interface EtapaObra {
  etapa_id: number
  obra: number
  nome_etapa: string
  ordem: number
  percentual_conclusao: string
  responsavel: number | null
  data_inicio_prevista: string | null
  data_fim_prevista: string | null
  data_inicio_real: string | null
  data_fim_real: string | null
  status_etapa: StatusObra
  descricao: string | null
  orcamento_previsto: string | null
  data_cadastro: string
  data_atualizacao: string
}

export interface EtapaObraFormData {
  obra: number
  nome_etapa: string
  ordem: number
  percentual_conclusao: string
  status_etapa: StatusObra
  descricao: string
  data_inicio_prevista: string
  data_fim_prevista: string
  orcamento_previsto: string
}

export interface DocumentoObra {
  documento_id: number
  obra: number
  nome_documento: string
  tipo_documento: string
  versao: string | null
  descricao: string | null
  data_emissao: string | null
  responsavel: number | null
  arquivo: string
  status_documento: string
  data_aprovacao: string | null
  aprovador: number | null
  observacoes: string | null
  data_cadastro: string
  data_atualizacao: string
}

export interface AnaliseDocumentoResumo {
  id: number;
  nome: string;
  nome_original: string;
  nome_arquivo: string;
  obra_nome: string | null;
  autor_nome?: string | null;
  descricao: string | null;
  data_criacao: string;
  status_analise: string;
  data_analise: string | null;
  resultado_analise: unknown;
  tipo_analise: string | null;
  url_imagem: string | null;
  tem_analise: boolean;
}

export interface AnaliseDocumentoDetalhes {
  id: number;
  nome: string;
  nome_original: string;
  nome_arquivo: string;
  obra_nome: string;
  autor_nome?: string | null;
  descricao: string | null;
  data_criacao: string;
  status_analise: string;
  data_analise: string | null;
  resultado: unknown;
  resultado_analise: unknown;
  url_imagem: string | null;
  tem_analise: boolean;
}

export interface DocumentosAnaliseResponse {
  total: number;
  documentos: AnaliseDocumentoResumo[];
}

// ─── Fornecedores ─────────────────────────────────────────────────────────────

export type TipoContaFornecedor = 'corrente' | 'poupanca' | 'outro'

export interface Fornecedor {
  fornecedor_id: number
  razao_social: string
  cnpj: string
  contato: string
  email: string
  telefone: string
  tenant: number
}

export interface FornecedorFormData {
  razao_social: string
  cnpj: string
  contato: string
  email: string
  telefone: string
}

export interface DadoBancarioFornecedor {
  id: number
  fornecedor: number
  codigo_banco: string
  agencia: string
  agencia_dv: string | null
  conta: string
  conta_dv: string | null
  codigo_cedente: string | null
  carteira: string | null
  chave_pix: string | null
  tipo_conta: TipoContaFornecedor
  observacoes: string | null
  data_atualizacao: string
}

export interface DadoBancarioFornecedorFormData {
  fornecedor: number
  codigo_banco: string
  agencia: string
  agencia_dv: string
  conta: string
  conta_dv: string
  codigo_cedente: string
  carteira: string
  chave_pix: string
  tipo_conta: TipoContaFornecedor | ''
  observacoes: string
}

export interface ProdutoServicoFornecedor {
  id: number
  fornecedor: number | null
  nome_produto_servico: string
  descricao: string | null
  unidade_medida: string
  preco_unitario: string
  data_cotacao: string
  tipo_produto_servico: string
}

export interface ProdutoServicoFormData {
  fornecedor: number | null
  nome_produto_servico: string
  descricao: string
  unidade_medida: string
  preco_unitario: string
  tipo_produto_servico: string
}

// ─── RH ──────────────────────────────────────────────────────────────────────

export interface Cargo {
  cargo_id: number
  nome_cargo: string
  descricao: string
  departamento: string | null
  tenant: number
}

export interface CargoFormData {
  nome_cargo: string
  descricao: string
  departamento: string
}

export type StatusContratoFuncionario = 'ativo' | 'inativo' | 'ferias' | 'licenca' | 'desligado'
export type GeneroFuncionario = 'masculino' | 'feminino' | 'outro'
export type EstadoCivilFuncionario = 'solteiro' | 'casado' | 'divorciado' | 'viuvo' | 'uniao_estavel'

export interface Funcionario {
  funcionario_id: number
  usuario: number | null
  cargo: number | null
  empreendimento_vinculado: number | null
  nome_completo: string
  cpf: string
  rg: string | null
  data_nascimento: string
  genero: GeneroFuncionario
  estado_civil: EstadoCivilFuncionario | null
  telefone_pessoal: string | null
  telefone_celular: string | null
  email_pessoal: string | null
  endereco_completo: string
  data_admissao: string
  data_demissao: string | null
  salario_base: string | null
  status_contrato: StatusContratoFuncionario
  numero_ctps: string | null
  serie_ctps: string | null
  pis_pasep: string | null
  carteira_trabalho: string | null
  carteira_trabalho_data_emissao: string | null
  carteira_trabalho_serie: string | null
  carteira_trabalho_numero: string | null
  carteira_trabalho_uf: string | null
  carteira_trabalho_data_validade: string | null
  carteira_trabalho_observacoes: string | null
  data_cadastro: string
  data_atualizacao: string
  tenant: number
}

export interface FuncionarioFormData {
  nome_completo: string
  cpf: string
  rg: string
  data_nascimento: string
  genero: GeneroFuncionario | ''
  estado_civil: EstadoCivilFuncionario | ''
  telefone_pessoal: string
  telefone_celular: string
  email_pessoal: string
  endereco_completo: string
  cargo: number | ''
  empreendimento_vinculado: number | ''
  data_admissao: string
  data_demissao: string
  salario_base: string
  status_contrato: StatusContratoFuncionario
  numero_ctps: string
  serie_ctps: string
  pis_pasep: string
}

export interface DadoMedicoFuncionario {
  id: number
  funcionario: number
  numero_cartao_sus: string | null
  tipo_sanguineo: string | null
  alergias: string | null
  medicamentos: string | null
  historico_doencas: string | null
  contato_emergencia_nome: string | null
  contato_emergencia_telefone: string | null
  observacoes_medicas: string | null
}

export interface DadoMedicoFormData {
  funcionario: number
  numero_cartao_sus: string
  tipo_sanguineo: string
  alergias: string
  medicamentos: string
  historico_doencas: string
  contato_emergencia_nome: string
  contato_emergencia_telefone: string
  observacoes_medicas: string
}

export type TipoExameASO = 'admissional' | 'periodico' | 'demissional'
export type StatusASO = 'ativo' | 'inativo' | 'pendente' | 'cancelado'

export interface ASOFuncionario {
  aso_id: number
  funcionario: number
  tipo_exame: TipoExameASO
  status: StatusASO
  data_exame: string
  data_validade: string | null
  arquivo: string | null
  observacoes: string | null
}

export interface ASOFuncionarioFormData {
  funcionario: number
  tipo_exame: TipoExameASO | ''
  status: StatusASO
  data_exame: string
  data_validade: string
  observacoes: string
}

export interface DocumentoFuncionario {
  documento_id: number
  funcionario: number
  tipo_documento: 'rg' | 'cpf' | 'cnh' | 'ctps' | 'comprovante_residencia' | 'certificado_curso' | 'aso' | 'outros'
  nome_documento: string
  arquivo: string
  data_upload: string
}

export type TipoContaFuncionario =
  'corrente' | 'poupanca' | 'investimento' | 'salario' | 'conta_conjunta' | 'conta_empresarial' | 'outro'

export interface DadoBancarioFuncionario {
  id: number
  funcionario: number
  codigo_banco: string
  agencia: string
  agencia_dv: string | null
  conta: string
  conta_dv: string | null
  codigo_cedente: string | null
  carteira: string | null
  tipo_conta: TipoContaFuncionario
  chave_pix: string | null
  titular_nome: string
  titular_cpf_cnpj: string
  observacoes: string | null
  data_atualizacao: string
}

export interface DadoBancarioFuncionarioFormData {
  funcionario: number
  codigo_banco: string
  agencia: string
  agencia_dv: string
  conta: string
  conta_dv: string
  codigo_cedente: string
  carteira: string
  tipo_conta: TipoContaFuncionario | ''
  chave_pix: string
  titular_nome: string
  titular_cpf_cnpj: string
  observacoes: string
}

export type FormaPagamentoFuncionario =
  'dinheiro' | 'cartao_credito' | 'cartao_debito' | 'transferencia' | 'pix' | 'boleto' | 'deposito' | 'cheque' | 'outro'

export interface PagamentoFuncionario {
  id: number
  funcionario: number
  data_pagamento: string
  salario_base: string
  descontos: string
  adicionais: string
  extras: string
  bonus: string
  tipos_descontos: string | null
  tipos_adicionais: string | null
  tipos_extras: string | null
  tipos_bonus: string | null
  salario_liquido: string
  forma_pagamento: FormaPagamentoFuncionario
  parcela: number
  referencia_pagamento: string | null
  link_holerite: string | null
  observacoes: string | null
}

export interface PagamentoFormData {
  funcionario: number
  data_pagamento: string
  salario_base: string
  descontos: string
  adicionais: string
  extras: string
  bonus: string
  tipos_descontos: string
  tipos_adicionais: string
  tipos_extras: string
  tipos_bonus: string
  salario_liquido: string
  forma_pagamento: FormaPagamentoFuncionario | ''
  parcela: number
  referencia_pagamento: string
  link_holerite: string
  observacoes: string
}

export interface FolhaPagamento {
  folha_id: number
  funcionario: number
  mes_referencia: string
  salario_bruto: string
  total_descontos: string
  total_proventos: string
  salario_liquido: string
  data_pagamento: string | null
  holerite: string | null
}

export interface FolhaPagamentoFormData {
  funcionario: number
  mes_referencia: string
  salario_bruto: string
  total_descontos: string
  total_proventos: string
  salario_liquido: string
  data_pagamento: string
}
