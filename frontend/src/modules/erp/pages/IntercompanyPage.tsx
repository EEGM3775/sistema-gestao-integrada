import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft, ArrowRight, Handshake, Scale } from 'lucide-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Btn, Card, Empty, Loading, Modal, SectionHead } from '@/components/malha'
import { formatBRL, apiDecimalToCents } from '@/utils/money'
import { dateToBR, isoLocal } from '@/utils/dates'
import { parseApiErrors } from '@/utils/formErrors'
import { escolherEntidade } from '@/modules/entidades/entidadeAtiva'
import { erpClient } from '../api/erpClient'

const reais = (v: string) => formatBRL(apiDecimalToCents(v))

interface Saldo {
  credora: number
  credora_nome: string
  devedora: number
  devedora_nome: string
  saldo: string
}

interface Previa {
  a_recebe_de_b: string
  b_recebe_de_a: string
  compensavel: string
  saldo_final: string
  quem_fica_devendo: number | null
}

/**
 * Intercompany (docs/modulos/entidades.md §3): o que uma entidade do grupo deve
 * à outra porque pagou ou recebeu por ela — o rateio para o centro de custo da
 * outra, a cota da co-dona. Cada par nasce sozinho do título de origem; aqui se
 * vê o saldo entre cada dupla e se faz o **encontro de contas**, que compensa o
 * que as duas devem uma à outra e baixa os dois lados de uma vez.
 */
export default function IntercompanyPage() {
  const { data, isLoading } = useQuery({
    queryKey: ['erp', 'intercompany'],
    queryFn: async () => (await erpClient.get<{ saldos: Saldo[] }>('erp/intercompany/')).data,
  })
  const [dupla, setDupla] = useState<{ a: Saldo['credora']; b: Saldo['devedora']; nomes: [string, string] } | null>(null)
  const saldos = data?.saldos ?? []

  const duplas = new Map<string, { a: number; b: number; nomes: [string, string]; linhas: Saldo[] }>()
  for (const s of saldos) {
    const [a, b] = s.credora < s.devedora ? [s.credora, s.devedora] : [s.devedora, s.credora]
    const chave = `${a}-${b}`
    const nomes: [string, string] = s.credora < s.devedora ? [s.credora_nome, s.devedora_nome] : [s.devedora_nome, s.credora_nome]
    if (!duplas.has(chave)) duplas.set(chave, { a, b, nomes, linhas: [] })
    duplas.get(chave)!.linhas.push(s)
  }

  return (
    <div className="px-6 py-6 flex flex-col gap-5" style={{ color: 'var(--ink-2)', maxWidth: 980 }}>
      <div>
        <Link to="/app/erp" className="inline-flex items-center gap-1.5 text-xs font-semibold mb-2" style={{ color: 'var(--ink-3)', textDecoration: 'none' }}>
          <ArrowLeft size={14} /> ERP / Financeiro
        </Link>
        <h1 className="text-xl font-bold" style={{ color: 'var(--ink)' }}>Intercompany</h1>
        <p className="text-xs" style={{ color: 'var(--ink-3)', maxWidth: 680, lineHeight: 1.5 }}>
          Quando uma entidade paga ou recebe o que é de outra, o sistema gera na hora o par: a receber em uma,
          a pagar na outra. A despesa sai da DRE de quem pagou e entra na de quem consumiu. Aqui fica o saldo
          entre cada dupla — acerte por transferência (baixa comum) ou compense os dois lados.
        </p>
      </div>

      {isLoading && <Loading o="os saldos entre as entidades" />}
      {!isLoading && duplas.size === 0 && (
        <Empty>
          <Handshake size={22} />
          Nenhuma entidade deve nada a outra. O par aparece aqui quando um título é rateado para o centro de
          custo de outra entidade, ou quando o empreendimento tem co-donas sem empresa própria.
        </Empty>
      )}

      {[...duplas.values()].map(d => (
        <Card key={`${d.a}-${d.b}`}>
          <SectionHead
            sub="Saldo em aberto dos títulos intercompany entre as duas"
            right={
              <Btn tam="sm" onClick={() => setDupla({ a: d.a, b: d.b, nomes: d.nomes })}>
                <Scale size={14} /> Encontro de contas
              </Btn>
            }
          >
            {d.nomes[0]} ↔ {d.nomes[1]}
          </SectionHead>
          <div className="flex flex-col gap-2">
            {d.linhas.map(l => (
              <div key={`${l.credora}-${l.devedora}`} className="flex items-center gap-2 text-sm">
                <strong style={{ color: 'var(--ink)' }}>{l.devedora_nome}</strong>
                <span>deve a</span>
                <strong style={{ color: 'var(--ink)' }}>{l.credora_nome}</strong>
                <ArrowRight size={13} />
                <strong style={{ color: 'var(--ink)' }}>{reais(l.saldo)}</strong>
                <Link
                  to="/app/erp/contas-a-receber"
                  onClick={() => escolherEntidade(l.credora)}
                  className="text-xs font-semibold ml-auto"
                  style={{ color: 'var(--accent-ink)', textDecoration: 'none' }}
                >
                  Ver os títulos
                </Link>
              </div>
            ))}
          </div>
        </Card>
      ))}

      {dupla && <EncontroDialog {...dupla} onClose={() => setDupla(null)} />}
    </div>
  )
}

function EncontroDialog({ a, b, nomes, onClose }: { a: number; b: number; nomes: [string, string]; onClose: () => void }) {
  const qc = useQueryClient()
  const [data, setData] = useState(isoLocal(new Date()))
  const previa = useQuery({
    queryKey: ['erp', 'intercompany', 'previa', a, b],
    queryFn: async () => (await erpClient.get<Previa>('erp/intercompany/encontro/', { params: { a, b } })).data,
  })
  const compensar = useMutation({
    mutationFn: async () => (await erpClient.post('erp/intercompany/encontro/', { a, b, data })).data,
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['erp'] })
      onClose()
    },
  })
  const p = previa.data
  const erro = compensar.error ? parseApiErrors(compensar.error) : {}
  const nada = p ? apiDecimalToCents(p.compensavel) === 0 : true
  const devedor = p?.quem_fica_devendo === a ? nomes[0] : p?.quem_fica_devendo === b ? nomes[1] : null

  return (
    <Modal
      titulo={`Encontro de contas — ${nomes[0]} ↔ ${nomes[1]}`}
      onClose={onClose}
      rodape={
        <>
          <Btn onClick={onClose}>Cancelar</Btn>
          <Btn variant="primary" disabled={nada || compensar.isPending} onClick={() => compensar.mutate()}>
            {compensar.isPending ? 'Compensando…' : p ? `Compensar ${reais(p.compensavel)}` : 'Compensar'}
          </Btn>
        </>
      }
    >
      {previa.isLoading && <Loading o="a prévia" />}
      {p && (
        <div className="flex flex-col gap-3 text-sm" style={{ lineHeight: 1.5 }}>
          <p>{nomes[0]} tem a receber de {nomes[1]}: <strong>{reais(p.a_recebe_de_b)}</strong></p>
          <p>{nomes[1]} tem a receber de {nomes[0]}: <strong>{reais(p.b_recebe_de_a)}</strong></p>
          {nada ? (
            <p style={{ color: 'var(--ink-3)' }}>
              Só uma das duas tem a receber — não há o que compensar. Acerte por transferência, dando baixa nos títulos.
            </p>
          ) : (
            <p>
              Compensa <strong>{reais(p.compensavel)}</strong> dos dois lados, dos títulos mais antigos para os mais
              novos, com o meio "Compensação".{' '}
              {devedor ? <>Depois, {devedor} ainda fica devendo <strong>{reais(p.saldo_final)}</strong>.</> : 'Depois, ninguém deve nada.'}
            </p>
          )}
          <label className="flex flex-col gap-1">
            <span className="text-xs font-semibold" style={{ color: 'var(--ink)' }}>Data da compensação</span>
            <input type="date" value={data} onChange={e => setData(e.target.value)}
              style={{ padding: '7px 10px', borderRadius: 8, border: '1px solid var(--line)', background: 'var(--surface)', color: 'var(--ink)', maxWidth: 200 }} />
            <span className="text-xs" style={{ color: 'var(--ink-3)' }}>As baixas entram no caixa das duas com {dateToBR(data)}.</span>
          </label>
          {(erro._form || erro.detail) && <p style={{ color: 'var(--danger-ink)' }}>{erro._form ?? erro.detail}</p>}
        </div>
      )}
    </Modal>
  )
}
