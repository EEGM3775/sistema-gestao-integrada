import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Building2, CheckCircle2, Download, Files, Loader2, X } from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import { formatBRL, apiDecimalToCents } from '@/utils/money'
import { dateToBR, maxCalendarioISO, maxTodayISO } from '@/utils/dates'
import { parseApiErrors } from '@/utils/formErrors'
import {
  useAndamentoLote, useBaixarRemessa, useCarteiras, useEmitirLoteNfse, useGerarLote, usePreviaLote, usePreviaLoteNfse,
} from '../hooks/useCobranca'
import type { EscolhaDoLote } from '../api/endpoints/cobranca'
import type { AndamentoLote, PreviaLote, RemessaCnab } from '../types'
import { ResultadoNotas } from './EmitirNotasLoteDialog'
import { buttonPrimaryStyle, buttonSecondaryStyle } from './forms/formStyles'

const reais = (v?: string) => formatBRL(apiDecimalToCents(v ?? '0'))

/**
 * Boletos em lote (item 52 do dono). Três passos na mesma janela: a prévia
 * (quantos saem, quantos já têm boleto, quantos vão como segunda via e por
 * quanto), a escolha do canal — Asaas ou a carteira de cobrança do banco
 * (CNAB) — e o andamento, conta a conta, com o motivo de quem não saiu.
 *
 * **E as notas junto** (pedido do dono, 01/10/2026): marcada a opção, as mesmas
 * contas ganham a NFS-e logo depois dos boletos — a nota do mês sai com o carnê.
 */
export function GerarBoletosLoteDialog({ escolha, quantidade, onFechar }: {
  escolha: EscolhaDoLote
  quantidade: number
  onFechar: () => void
}) {
  const [canal, setCanal] = useState<'asaas' | 'cnab'>('asaas')
  const [carteira, setCarteira] = useState<number | undefined>()
  const [vencimento, setVencimento] = useState<string | undefined>()
  const [loteId, setLoteId] = useState<number | undefined>()
  const { hasPermission } = useAuth()
  const podeNota = hasPermission('erp.nf.emitir')
  const [comNotas, setComNotas] = useState(false)
  const previa = usePreviaLote()
  const previaNotas = usePreviaLoteNfse()
  const emitirNotas = useEmitirLoteNfse()
  const gerar = useGerarLote()
  const carteiras = useCarteiras()
  const andamento = useAndamentoLote(loteId)
  const ativas = (carteiras.data ?? []).filter(c => c.ativa)

  const refazer = previa.mutate
  const escolhaComData = { ...escolha, vencimento_segunda_via: vencimento }
  const chave = JSON.stringify(escolhaComData)
  useEffect(() => { refazer(JSON.parse(chave) as EscolhaDoLote) }, [chave, refazer])
  useEffect(() => { if (!carteira && ativas.length) setCarteira(ativas[0].conta_cobranca_id) }, [ativas, carteira])
  const refazerNotas = previaNotas.mutate
  const chaveNotas = JSON.stringify(escolha)
  useEffect(() => { if (comNotas) refazerNotas(JSON.parse(chaveNotas) as EscolhaDoLote) }, [comNotas, chaveNotas, refazerNotas])

  const emitirTudo = () => gerar.mutate({ escolha: escolhaComData, canal, carteira }, {
    onSuccess: r => {
      setLoteId(r.lote_id)
      if (comNotas) emitirNotas.mutate(escolha)
    },
  })

  const p = previa.data
  const erro = previa.error ? parseApiErrors(previa.error)._form : gerar.error ? parseApiErrors(gerar.error)._form : null
  const cabeNoBanco = !p || p.boletos_sem_cadastro < p.total_boletos
  const podeGerar = p && p.total_boletos > 0 && !gerar.isPending && (canal === 'asaas' || (carteira && cabeNoBanco))

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center px-4">
      <div className="absolute inset-0" style={{ background: 'rgba(15, 23, 42, 0.45)' }} onClick={() => !gerar.isPending && onFechar()} aria-hidden="true" />
      <div role="dialog" aria-modal="true" aria-label="Gerar boletos em lote" className="relative w-full flex flex-col rounded-xl"
        style={{ maxWidth: 560, maxHeight: '90vh', background: 'var(--surface)', boxShadow: 'var(--shadow-lg)', border: '1px solid var(--line)' }}>
        <header className="flex items-center gap-2.5 px-5 py-4" style={{ borderBottom: '1px solid var(--line)' }}>
          <Files size={18} style={{ color: 'var(--accent-ink)' }} />
          <h2 className="text-base font-bold" style={{ color: 'var(--ink)' }}>Gerar boletos — {quantidade.toLocaleString('pt-BR')} conta{quantidade !== 1 ? 's' : ''}</h2>
          <button type="button" onClick={onFechar} aria-label="Fechar" style={{ marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer', color: 'var(--ink-3)' }}><X size={18} /></button>
        </header>

        <div className="flex-1 overflow-y-auto px-5 py-4 flex flex-col gap-4 text-sm" style={{ color: 'var(--ink-2)' }}>
          {loteId ? (
            <>
              <Andamento dados={andamento.data} />
              {comNotas && (
                <div style={{ borderTop: '1px solid var(--line)', paddingTop: 12 }}>
                  {emitirNotas.isPending && <p className="flex items-center gap-2"><Loader2 size={15} className="animate-spin" /> Enviando as notas fiscais…</p>}
                  {emitirNotas.data && <ResultadoNotas resultado={emitirNotas.data} />}
                  {emitirNotas.error && <p style={{ color: 'var(--danger-ink)' }}>⚠ Notas fiscais: {parseApiErrors(emitirNotas.error)._form}</p>}
                </div>
              )}
            </>
          ) : (
            <>
              {!p && previa.isPending && <p className="flex items-center gap-2"><Loader2 size={15} className="animate-spin" /> Conferindo as contas…</p>}
              {p && (
                <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5" style={{ background: 'var(--surface-2)', borderRadius: 'var(--r-md)', padding: '10px 12px' }}>
                  <dt>Boletos novos</dt><dd className="text-right font-semibold">{p.emitir}</dd>
                  <dt>Segunda via (vencidas, com multa e juros)</dt><dd className="text-right font-semibold">{p.segunda_via}</dd>
                  <dt>Já têm boleto válido — ficam de fora</dt><dd className="text-right">{p.com_boleto_valido}</dd>
                  <dt>Quitadas ou canceladas — ficam de fora</dt><dd className="text-right">{p.encerradas}</dd>
                  <dt className="font-bold" style={{ color: 'var(--ink)' }}>Total a cobrar</dt>
                  <dd className="text-right font-bold" style={{ color: 'var(--ink)' }}>{reais(p.valor_total)}</dd>
                  {Number(p.encargos_total) > 0 && <><dt>dos quais multa e juros</dt><dd className="text-right">{reais(p.encargos_total)}</dd></>}
                </dl>
              )}

              {p && (
                <p style={{ fontSize: 12, color: 'var(--ink-3)', marginTop: -8 }}>
                  Até {p.teto.toLocaleString('pt-BR')} boletos por lote nesta empresa.{' '}
                  <Link to="/app/erp/configuracoes" style={{ color: 'var(--accent-ink)', fontWeight: 600 }}>Ver o limite</Link>
                </p>
              )}

              {p && p.segunda_via > 0 && (
                <label className="flex flex-col gap-1">
                  <span style={{ fontWeight: 600 }}>Nova data das vencidas</span>
                  <input type="date" min={maxTodayISO()} max={maxCalendarioISO}
                    value={vencimento ?? p.vencimento_segunda_via ?? ''}
                    onChange={e => e.target.value && setVencimento(e.target.value)}
                    style={{ border: '1.5px solid var(--line)', borderRadius: 'var(--r-sm)', padding: '7px 10px', background: 'var(--surface)', color: 'var(--ink)', maxWidth: 200 }} />
                  <span style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>Cada boleto ainda anda para o próximo dia útil da praça do imóvel.</span>
                </label>
              )}

              <fieldset className="flex flex-col gap-2">
                <legend style={{ fontWeight: 600, marginBottom: 6 }}>Por onde emitir</legend>
                <label className="flex items-start gap-2 cursor-pointer">
                  <input type="radio" checked={canal === 'asaas'} onChange={() => setCanal('asaas')} style={{ marginTop: 3 }} />
                  <span><strong>Asaas</strong> — o gateway registra, envia e avisa o pagamento sozinho.</span>
                </label>
                <label className="flex items-start gap-2 cursor-pointer">
                  <input type="radio" checked={canal === 'cnab'} onChange={() => setCanal('cnab')} style={{ marginTop: 3 }} />
                  <span><strong>Banco (CNAB)</strong> — gera o arquivo de remessa para a sua carteira de cobrança; o pagamento chega pelo arquivo de retorno.</span>
                </label>
                {canal === 'cnab' && (
                  ativas.length ? (
                    <select value={carteira ?? ''} onChange={e => setCarteira(Number(e.target.value))}
                      style={{ border: '1.5px solid var(--line)', borderRadius: 'var(--r-sm)', padding: '7px 10px', background: 'var(--surface)', color: 'var(--ink)' }}>
                      {ativas.map(c => <option key={c.conta_cobranca_id} value={c.conta_cobranca_id}>{c.nome} · {c.banco_nome} · CNAB {c.layout}</option>)}
                    </select>
                  ) : (
                    <p style={{ fontSize: 12.5 }}>
                      Nenhuma carteira de cobrança cadastrada. <Link to="/app/erp/cobranca-bancaria" style={{ color: 'var(--accent-ink)', fontWeight: 600 }}>Cadastrar carteira</Link>
                    </p>
                  )
                )}
                {canal === 'cnab' && p && p.cadastro_incompleto_total > 0 && <CadastroIncompleto previa={p} />}
              </fieldset>

              {podeNota && (
                <label className="flex items-start gap-2 cursor-pointer" style={{ padding: '10px 12px', borderRadius: 'var(--r-md)', border: '1px solid var(--line)' }}>
                  <input type="checkbox" checked={comNotas} onChange={e => setComNotas(e.target.checked)} style={{ marginTop: 3 }} />
                  <span className="flex flex-col gap-0.5">
                    <strong>Emitir também a nota fiscal de cada conta</strong>
                    <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>
                      {!comNotas ? 'A NFS-e sai pela NFE.io logo depois dos boletos.'
                        : previaNotas.isPending ? 'Conferindo os cadastros…'
                        : previaNotas.data ? `${previaNotas.data.emitir} nota${previaNotas.data.emitir !== 1 ? 's' : ''} a emitir · ${previaNotas.data.com_nota} já têm nota${previaNotas.data.sem_cadastro ? ` · ${previaNotas.data.sem_cadastro} sem cadastro completo (ficam de fora)` : ''}.`
                        : previaNotas.error ? (parseApiErrors(previaNotas.error)._form ?? 'Não foi possível conferir as notas.') : ''}
                    </span>
                  </span>
                </label>
              )}
            </>
          )}
          {erro && <p style={{ color: 'var(--danger-ink)' }}>⚠ {erro}</p>}
        </div>

        <footer className="flex items-center justify-end gap-2 px-5 py-3.5" style={{ borderTop: '1px solid var(--line)', background: 'var(--surface-2)' }}>
          {loteId ? (
            <button type="button" onClick={onFechar} style={buttonPrimaryStyle}>Fechar</button>
          ) : (
            <>
              <button type="button" onClick={onFechar} style={buttonSecondaryStyle}>Cancelar</button>
              <button type="button" disabled={!podeGerar}
                onClick={emitirTudo}
                style={{ ...buttonPrimaryStyle, opacity: podeGerar ? 1 : 0.6, cursor: gerar.isPending ? 'wait' : 'pointer' }}>
                {gerar.isPending ? 'Emitindo…' : `Emitir ${p?.total_boletos ?? ''} boleto${p?.total_boletos === 1 ? '' : 's'}${comNotas ? ' e notas' : ''}`}
              </button>
            </>
          )}
        </footer>
      </div>
    </div>
  )
}

/** Quem o banco recusaria — dito antes de emitir, com o caminho para completar. */
function CadastroIncompleto({ previa }: { previa: PreviaLote }) {
  const todos = previa.boletos_sem_cadastro >= previa.total_boletos
  return (
    <div style={{ padding: '10px 12px', borderRadius: 'var(--r-md)', background: 'var(--accent-soft)', color: 'var(--accent-ink)', fontSize: 12.5 }}>
      <p className="font-semibold">
        {todos
          ? 'Nenhum destes boletos pode ir para o banco: falta o endereço dos pagadores.'
          : `${previa.boletos_sem_cadastro} boleto${previa.boletos_sem_cadastro !== 1 ? 's' : ''} ficam fora: falta o endereço dos pagadores.`}
      </p>
      <p className="mt-1">O banco só registra o boleto com CPF/CNPJ, endereço, CEP, cidade e UF do pagador. Complete o cadastro (abre em outra aba) e gere de novo — ou emita pelo Asaas, que não exige endereço.</p>
      <ul className="flex flex-col gap-0.5 mt-2">
        {previa.cadastro_incompleto.map(c => (
          <li key={c.cliente_id}>
            <Link to={`/app/clientes/${c.cliente_id}`} target="_blank" rel="noreferrer" style={{ color: 'inherit', fontWeight: 600 }}>{c.cliente_nome}</Link>
            {' '}— falta {c.falta.join(', ')}
          </li>
        ))}
        {previa.cadastro_incompleto_total > previa.cadastro_incompleto.length && (
          <li>e mais {previa.cadastro_incompleto_total - previa.cadastro_incompleto.length}.</li>
        )}
      </ul>
    </div>
  )
}

function Andamento({ dados }: { dados?: AndamentoLote }) {
  const baixar = useBaixarRemessa()
  if (!dados) return <p className="flex items-center gap-2"><Loader2 size={15} className="animate-spin" /> Emitindo…</p>
  const feitos = dados.emitidos + dados.erros
  const pct = dados.total ? Math.round((feitos / dados.total) * 100) : 100
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2 font-semibold" style={{ color: 'var(--ink)' }}>
        {dados.pendentes ? <Loader2 size={16} className="animate-spin" /> : <CheckCircle2 size={16} style={{ color: 'var(--good-ink)' }} />}
        {dados.pendentes ? `Emitindo… ${feitos} de ${dados.total}` : `${dados.emitidos} boleto${dados.emitidos !== 1 ? 's' : ''} emitido${dados.emitidos !== 1 ? 's' : ''}`}
      </div>
      <div style={{ height: 6, background: 'var(--surface-2)', borderRadius: 999 }}>
        <div style={{ width: `${pct}%`, height: '100%', background: 'var(--accent)', borderRadius: 999, transition: 'width .3s' }} />
      </div>
      {dados.canal === 'cnab' && dados.remessa_id && (
        <div className="flex items-center gap-2" style={{ padding: '10px 12px', borderRadius: 'var(--r-md)', background: 'var(--surface-2)' }}>
          <Building2 size={16} />
          <span>Envie o arquivo de remessa pelo internet banking da empresa. O banco registra os boletos e devolve o retorno.</span>
          <button type="button" disabled={baixar.isPending}
            onClick={() => baixar.mutate({ remessa_id: dados.remessa_id!, nome_arquivo: dados.remessa_nome ?? `remessa-${dados.remessa_id}.REM` } as RemessaCnab)}
            className="flex items-center gap-1.5" style={{ ...buttonSecondaryStyle, marginLeft: 'auto', whiteSpace: 'nowrap' }}>
            <Download size={14} /> Baixar remessa
          </button>
        </div>
      )}
      {dados.erros > 0 && (
        <div>
          <p className="font-semibold" style={{ color: 'var(--danger-ink)' }}>{dados.erros} conta{dados.erros !== 1 ? 's' : ''} não saíram:</p>
          <ul className="flex flex-col gap-1 mt-1" style={{ fontSize: 12.5 }}>
            {dados.falhas.map(f => (
              <li key={f.conta_receber_id}><strong>{f.cliente_nome}</strong> · {f.descricao} — {f.mensagem}</li>
            ))}
          </ul>
        </div>
      )}
      <p style={{ fontSize: 12, color: 'var(--ink-3)' }}>Lote nº {dados.lote_id} · {dateToBR(dados.criado_em.slice(0, 10))}. Pode fechar esta janela: a emissão continua.</p>
    </div>
  )
}
