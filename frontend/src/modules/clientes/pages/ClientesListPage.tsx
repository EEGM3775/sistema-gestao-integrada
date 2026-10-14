import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, Users } from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'
import { BotaoExportar, Empty, Loading, WizardImportacao } from '@/components/malha'
import ClienteForm from '../components/ClienteForm'
import { createCliente } from '../hooks/useCliente'
import type { ClienteFormData } from '@/types'
import { BarraCarteira } from '../carteira/BarraCarteira'
import { Grade, montarArvore, type ItemGrade, type NoGrupo } from '../carteira/Grade'
import { COLUNA_ANCORA, colunasDisponiveis, colunasVisiveis } from '../carteira/colunas'
import {
  PAGINA_DO_GRUPO, useCarteira, useGruposCarteira, useLinhasDeGrupos, useOpcoesCarteira,
} from '../carteira/hooks'
import { usePreferenciasCarteira } from '../carteira/preferencias'
import type { FiltrosCarteira, LinhaCarteira } from '../carteira/types'

/**
 * Carteira de clientes — a folha única da tela de Clientes.
 *
 * A tela antiga baixava a tabela inteira e refazia a requisição a cada tecla:
 * com milhares de cadastros isso é insustentável. Aqui a lista é paginada com
 * rolagem infinita, a busca é debounced, e o usuário escolhe **o que é uma
 * linha** (cliente ou unidade) e **como as linhas se juntam** (agrupar por
 * empreendimento, quadra, cidade, faixa de atraso…) — o modelo de *row
 * grouping* dos grids corporativos, que é o mais perto de Excel que uma tela
 * ligada a um banco multiusuário consegue ser sem mentir sobre os números.
 */
export default function ClientesListPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { visao, prefs, alterar, trocarVisao } = usePreferenciasCarteira()
  const [filtros, setFiltros] = useState<FiltrosCarteira>({})
  const [buscaDigitada, setBuscaDigitada] = useState('')
  const [abertos, setAbertos] = useState<ReadonlySet<string>>(new Set())
  const [formAberto, setFormAberto] = useState(false)

  const { data: opcoes } = useOpcoesCarteira()

  // Debounce: sem isso cada tecla vira uma consulta ao banco inteiro.
  useEffect(() => {
    const t = setTimeout(() => setFiltros(f => ({ ...f, busca: buscaDigitada || undefined })), 300)
    return () => clearTimeout(t)
  }, [buscaDigitada])

  const agrupado = prefs.agrupamento.length > 0

  const lista = useCarteira({ visao, filtros, ordenar: prefs.ordenar, ativo: !agrupado })
  const grupos = useGruposCarteira({ visao, filtros, niveis: prefs.agrupamento, ativo: agrupado })

  const arvore = useMemo(
    () => (agrupado ? montarArvore(grupos.grupos, prefs.agrupamento.length) : []),
    [agrupado, grupos.grupos, prefs.agrupamento.length],
  )

  // Só os grupos-folha abertos puxam linhas — abrir um nível intermediário
  // apenas revela os filhos, que já vieram no mesmo GROUP BY.
  const folhasAbertas = useMemo(() => {
    const saida: NoGrupo[] = []
    const andar = (nos: NoGrupo[]) => {
      for (const no of nos) {
        const chave = no.chaves.join('␟')
        if (!abertos.has(chave)) continue
        if (no.folha) saida.push(no)
        else andar(no.filhos)
      }
    }
    andar(arvore)
    return saida
  }, [arvore, abertos])

  // Quantas páginas de cada grupo aberto já foram pedidas. Recomeça quando o
  // recorte muda (filtro, ordem, visão, agrupamento): a página 3 de outro
  // critério não é a página 3 deste.
  const [paginasDoGrupo, setPaginasDoGrupo] = useState<ReadonlyMap<string, number>>(new Map())
  useEffect(() => { setPaginasDoGrupo(new Map()) }, [visao, filtros, prefs.ordenar, prefs.agrupamento])

  const linhasDeGrupo = useLinhasDeGrupos({
    visao, filtros, ordenar: prefs.ordenar, abertos: folhasAbertas, paginas: paginasDoGrupo,
  })

  const maisDoGrupo = useCallback((chave: string) => {
    setPaginasDoGrupo(atual => new Map(atual).set(chave, (atual.get(chave) ?? 1) + 1))
  }, [])

  const podeFinanceiro = agrupado ? grupos.podeFinanceiro : lista.podeFinanceiro
  const podeDocumento = agrupado ? grupos.podeDocumento : lista.podeDocumento
  const colunas = useMemo(
    () => colunasVisiveis(visao, prefs.colunas, podeFinanceiro),
    [visao, prefs.colunas, podeFinanceiro],
  )

  /** A lista achatada que a grade desenha: grupos, linhas e avisos, em ordem. */
  const itens = useMemo<ItemGrade[]>(() => {
    if (!agrupado) return lista.linhas.map(linha => ({ tipo: 'linha', linha, nivel: 0 }))

    const saida: ItemGrade[] = []
    const andar = (nos: NoGrupo[], nivel: number) => {
      for (const no of nos) {
        const chave = no.chaves.join('␟')
        const aberto = abertos.has(chave)
        saida.push({ tipo: 'grupo', no, nivel, aberto })
        if (!aberto) continue
        if (!no.folha) {
          andar(no.filhos, nivel + 1)
          continue
        }
        const carregado = linhasDeGrupo.get(chave)
        if (!carregado || carregado.carregando) {
          saida.push({ tipo: 'aviso', texto: 'Carregando as linhas do grupo…', nivel: nivel + 1 })
          continue
        }
        carregado.linhas.forEach(linha => saida.push({ tipo: 'linha', linha, nivel: nivel + 1 }))
        if (carregado.total > carregado.linhas.length) {
          const restantes = carregado.total - carregado.linhas.length
          saida.push({
            tipo: 'mais',
            chave,
            texto: `Carregar mais ${Math.min(restantes, PAGINA_DO_GRUPO)} (${carregado.linhas.length} de ${carregado.total})`,
            nivel: nivel + 1,
            buscando: carregado.buscandoMais,
          })
        }
      }
    }
    andar(arvore, 0)
    return saida
  }, [agrupado, lista.linhas, arvore, abertos, linhasDeGrupo])

  /**
   * O contador da barra: **o mesmo número, agrupado ou não**.
   *
   * Antes ele somava os cabeçalhos quando havia agrupamento — e a soma dos
   * cabeçalhos não é o total de clientes. Agrupar pessoas por empreendimento
   * coloca quem comprou em dois lugares nos dois grupos (cada grupo conta
   * distinto, e está certo dentro dele), então a soma passava de 5.000 para
   * 5.312 e o usuário via o número de clientes mudar por ter clicado em
   * "agrupar por". Agora o total vem do servidor, contado distinto sobre o
   * mesmo recorte, e a diferença — quando existe — é explicada ao lado.
   */
  const totalLinhas = agrupado ? grupos.total : lista.total
  const repetidosEmGrupos = agrupado
    ? Math.max(0, grupos.somaDosGrupos - grupos.total)
    : 0

  const alternarGrupo = useCallback((no: NoGrupo) => {
    const chave = no.chaves.join('␟')
    setAbertos(atual => {
      const proximo = new Set(atual)
      if (proximo.has(chave)) proximo.delete(chave)
      else proximo.add(chave)
      return proximo
    })
  }, [])

  const ordenarPor = useCallback((chave: string, sentido: 'asc' | 'desc') => {
    alterar('ordenar', sentido === 'desc' ? `-${chave}` : chave)
  }, [alterar])

  /** A âncora da visão (Cliente / Unidade) não sai do lugar: é a coluna
   *  congelada, a que abre a ficha e a que dá sentido à visão escolhida. */
  const reordenarColunas = useCallback((de: string, para: string) => {
    const ancora = COLUNA_ANCORA[visao]
    if (de === ancora || para === ancora) return
    const atual = colunas.map(c => c.chave)
    const origem = atual.indexOf(de)
    const destino = atual.indexOf(para)
    if (origem < 0 || destino < 0) return
    atual.splice(destino, 0, ...atual.splice(origem, 1))
    alterar('colunas', atual)
  }, [colunas, alterar, visao])

  const criar = async (dados: ClienteFormData) => {
    await createCliente(dados)
    queryClient.invalidateQueries({ queryKey: ['clientes', 'carteira'] })
  }

  const carregando = agrupado ? grupos.carregando : lista.carregando
  const vazio = !carregando && itens.length === 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: 'var(--ground)' }}>
      <header
        style={{
          display: 'flex', alignItems: 'center', gap: 12, padding: '14px 18px',
          background: 'var(--surface)', borderBottom: '1px solid var(--line)',
        }}
      >
        <span
          style={{
            width: 34, height: 34, borderRadius: 'var(--r-sm)', display: 'grid', placeItems: 'center',
            background: 'color-mix(in srgb, var(--st-neg) 14%, var(--surface-2))', color: 'var(--st-neg)',
          }}
        >
          <Users size={18} strokeWidth={1.9} />
        </span>
        <div style={{ minWidth: 0 }}>
          <h1 style={{ fontSize: 17, fontWeight: 700, color: 'var(--ink)', letterSpacing: '-0.02em' }}>
            Clientes
          </h1>
          <p style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>
            Carteira de compradores — unidades, contratos e situação de pagamento
          </p>
        </div>
        {/* Planilha da carteira: sai no recorte da barra (R7) e entra só nova. */}
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          <BotaoExportar
            recurso="cadastro.cliente"
            recorte={filtros as Record<string, string | number | undefined>}
          />
          <WizardImportacao
            recurso="cadastro.cliente"
            onConcluida={() => queryClient.invalidateQueries({ queryKey: ['clientes', 'carteira'] })}
          />
        </div>
        <button
          onClick={() => setFormAberto(true)}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 7,
            padding: '8px 14px', borderRadius: 'var(--r-sm)', border: 'none', cursor: 'pointer',
            background: 'var(--accent)', color: '#1A1204', fontSize: 13, fontWeight: 650,
          }}
        >
          <Plus size={15} /> Novo cliente
        </button>
      </header>

      <BarraCarteira
        visao={visao}
        onVisao={v => { trocarVisao(v); setAbertos(new Set()) }}
        busca={buscaDigitada}
        onBusca={setBuscaDigitada}
        agrupamento={prefs.agrupamento}
        onAgrupamento={n => { alterar('agrupamento', n); setAbertos(new Set()) }}
        colunas={colunasDisponiveis(visao, podeFinanceiro)}
        colunasVisiveis={colunas.map(c => c.chave)}
        ancora={COLUNA_ANCORA[visao]}
        onColunas={c => alterar('colunas', c)}
        filtros={filtros}
        onFiltros={setFiltros}
        opcoes={opcoes}
        total={totalLinhas}
        repetidosEmGrupos={repetidosEmGrupos}
        podeFinanceiro={podeFinanceiro}
      />

      {carregando ? (
        <Loading o={agrupado ? 'os grupos da carteira' : 'a carteira'} />
      ) : vazio ? (
        <div style={{ padding: 24 }}>
          <Empty>
            {filtros.busca || Object.values(filtros).some(Boolean)
              ? 'Nenhum resultado para os filtros aplicados.'
              : 'Nenhum cliente cadastrado ainda. O primeiro cadastro abre a carteira.'}
          </Empty>
        </div>
      ) : (
        <Grade
          itens={itens}
          colunas={colunas}
          larguras={prefs.larguras}
          ordenar={prefs.ordenar}
          podeFinanceiro={podeFinanceiro}
          podeDocumento={podeDocumento}
          carregando={lista.buscandoMais}
          onOrdenar={ordenarPor}
          onLargura={(chave, largura) => alterar('larguras', { ...prefs.larguras, [chave]: largura })}
          onReordenar={reordenarColunas}
          onAbrir={(linha: LinhaCarteira) => navigate(`/app/clientes/${linha.clienteId}`)}
          onAlternarGrupo={alternarGrupo}
          onMaisDoGrupo={maisDoGrupo}
          onFimDaLista={() => { if (!agrupado && lista.temMais && !lista.buscandoMais) lista.proximaPagina() }}
        />
      )}

      <ClienteForm open={formAberto} onClose={() => setFormAberto(false)} onSave={criar} />
    </div>
  )
}
