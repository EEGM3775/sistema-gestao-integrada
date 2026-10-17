import { SelectComBusca, type SelectComBuscaProps } from './SelectComBusca'

/**
 * Os cadastros grandes já configurados para o `SelectComBusca` — o formulário
 * escolhe um fornecedor, funcionário, obra ou empreendimento **pela busca no
 * servidor**, nunca montando um `<select>` com a lista inteira (F2).
 *
 * Os quatro endpoints paginam **sob pedido** (`nucleo/paginacao.py`): o seletor
 * manda `?page=` e recebe páginas; a tela de lista de cada cadastro, que não
 * manda, segue recebendo tudo. O desempate pelo id deixa os nomes iguais em
 * ordem estável entre as páginas.
 */
type Fixas = 'recurso' | 'idDe' | 'rotuloDe' | 'detalheDe' | 'ordenacao'
type SeletorProps<T> = Omit<SelectComBuscaProps<T>, Fixas>

interface FornecedorItem { fornecedor_id: number; razao_social: string; cnpj?: string | null; contato?: string }
interface FuncionarioItem { funcionario_id: number; nome_completo: string; cargo_nome?: string | null }
interface ObraItem { obra_id: number; nome_obra: string; endereco?: string; empreendimento?: number | null }
interface EmpreendimentoItem { empreendimento_id: number; empreendimento: string; cidade?: string; razao_social?: string }

export function SeletorDeFornecedor(props: SeletorProps<FornecedorItem>) {
  return (
    <SelectComBusca<FornecedorItem>
      recurso="/fornecedores/"
      idDe={f => f.fornecedor_id}
      rotuloDe={f => f.razao_social}
      detalheDe={f => [f.cnpj, f.contato].filter(Boolean).join(' · ') || null}
      ordenacao="razao_social,fornecedor_id"
      placeholder="Busque o fornecedor pelo nome ou CNPJ…"
      vazio="Nenhum fornecedor cadastrado."
      {...props}
    />
  )
}

export function SeletorDeFuncionario(props: SeletorProps<FuncionarioItem>) {
  return (
    <SelectComBusca<FuncionarioItem>
      recurso="/funcionarios/"
      idDe={f => f.funcionario_id}
      rotuloDe={f => f.nome_completo}
      detalheDe={f => f.cargo_nome || null}
      ordenacao="nome_completo,funcionario_id"
      placeholder="Busque o funcionário pelo nome…"
      vazio="Nenhum funcionário cadastrado."
      {...props}
    />
  )
}

export function SeletorDeObra(props: SeletorProps<ObraItem>) {
  return (
    <SelectComBusca<ObraItem>
      recurso="/obras/"
      idDe={o => o.obra_id}
      rotuloDe={o => o.nome_obra}
      detalheDe={o => o.endereco || null}
      ordenacao="nome_obra,obra_id"
      placeholder="Busque a obra pelo nome ou endereço…"
      vazio="Nenhuma obra cadastrada."
      {...props}
    />
  )
}

export function SeletorDeEmpreendimento(props: SeletorProps<EmpreendimentoItem>) {
  return (
    <SelectComBusca<EmpreendimentoItem>
      recurso="/empreendimentos/"
      idDe={e => e.empreendimento_id}
      rotuloDe={e => e.empreendimento}
      detalheDe={e => e.cidade || e.razao_social || null}
      ordenacao="empreendimento,empreendimento_id"
      placeholder="Busque o empreendimento…"
      vazio="Nenhum empreendimento cadastrado."
      {...props}
    />
  )
}
