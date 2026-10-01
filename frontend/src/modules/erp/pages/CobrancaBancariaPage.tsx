import { useRef, useState, type CSSProperties, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle, ArrowLeft, Building2, Download, Plus, Upload } from 'lucide-react'
import { Sheet } from '../components/shared/Sheet'
import { buttonPrimaryStyle, buttonSecondaryStyle, inputStyle, labelStyle, selectStyle } from '../components/forms/formStyles'
import {
  useBaixarRemessa, useBancosCnab, useCarteiras, useEnviarRetorno, useRemessas, useRetornos, useSalvarCarteira,
} from '../hooks/useCobranca'
import { apiDecimalToCents, formatBRL } from '@/utils/money'
import { dataHoraBR } from '@/utils/dates'
import { parseApiErrors } from '@/utils/formErrors'
import { maskCPFCNPJ, validateCPFCNPJ } from '@/utils/masks'
import type { CarteiraCobranca, RemessaCnab, RetornoCnab } from '../types'

/**
 * Cobrança registrada no banco — CNAB (item 52 do dono).
 *
 * O ciclo inteiro numa tela: a **carteira** (o contrato de cobrança da empresa
 * com o banco), as **remessas** que o SGI gerou para enviar pelo internet
 * banking, e os **retornos** que o banco devolve — é ao subir o retorno que os
 * boletos pagos dão baixa nas contas a receber.
 */
export default function CobrancaBancariaPage() {
  const carteiras = useCarteiras()
  const remessas = useRemessas()
  const retornos = useRetornos()
  const [editando, setEditando] = useState<Partial<CarteiraCobranca> | null>(null)

  return (
    <div className="px-6 py-6 flex flex-col gap-6" style={{ color: 'var(--ink-2)' }}>
      <div>
        <Link to="/app/erp/boletos" className="inline-flex items-center gap-1.5 text-xs font-semibold mb-2" style={{ color: 'var(--ink-3)', textDecoration: 'none' }}>
          <ArrowLeft size={14} /> Boletos
        </Link>
        <div className="flex items-end justify-between gap-3 flex-wrap">
          <div>
            <h1 className="text-xl font-bold" style={{ color: 'var(--ink)' }}>Cobrança bancária (CNAB)</h1>
            <p className="text-xs" style={{ color: 'var(--ink-3)' }}>
              Boletos registrados direto no banco da empresa: gere a remessa em Contas a receber, envie pelo internet banking e suba aqui o retorno.
            </p>
          </div>
          <button type="button" onClick={() => setEditando({ layout: '240', ativa: true })} className="flex items-center gap-2" style={buttonPrimaryStyle}>
            <Plus size={16} /> Nova carteira
          </button>
        </div>
      </div>

      <Secao titulo="Carteiras de cobrança">
        {carteiras.data?.length ? (
          <div className="grid gap-3" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))' }}>
            {carteiras.data.map(c => (
              <button key={c.conta_cobranca_id} type="button" onClick={() => setEditando(c)} className="text-left flex flex-col gap-1"
                style={{ border: '1px solid var(--line)', borderRadius: 'var(--r-md)', padding: 14, background: 'var(--surface)', cursor: 'pointer', opacity: c.ativa ? 1 : 0.6 }}>
                <span className="flex items-center gap-2 font-semibold" style={{ color: 'var(--ink)' }}><Building2 size={16} /> {c.nome}</span>
                <span style={{ fontSize: 12.5 }}>{c.banco_nome} · CNAB {c.layout} · ag. {c.agencia} · conta {c.conta}{c.conta_dv ? `-${c.conta_dv}` : ''}</span>
                <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>Próximo nosso número {c.proximo_nosso_numero} · próxima remessa nº {c.proximo_sequencial_remessa}</span>
                {c.problemas.length > 0 && (
                  <span className="flex items-center gap-1.5" style={{ fontSize: 12, color: 'var(--danger-ink)' }}>
                    <AlertTriangle size={13} /> Falta: {c.problemas.join(', ')}
                  </span>
                )}
                {!c.ativa && <span style={{ fontSize: 12 }}>Desativada</span>}
              </button>
            ))}
          </div>
        ) : (
          <p className="text-sm">
            {carteiras.isLoading ? 'Carregando…' : 'Nenhuma carteira cadastrada. Os dados vêm do contrato de cobrança que a empresa assinou com o banco (agência, conta, carteira e convênio).'}
          </p>
        )}
      </Secao>

      <EnviarRetorno carteiras={carteiras.data ?? []} />

      <Secao titulo="Remessas geradas">
        <TabelaRemessas remessas={remessas.data ?? []} carregando={remessas.isLoading} />
      </Secao>

      <Secao titulo="Retornos recebidos">
        <TabelaRetornos retornos={retornos.data ?? []} carregando={retornos.isLoading} />
      </Secao>

      <Sheet open={editando != null} onClose={() => setEditando(null)} width={520}
        title={editando?.conta_cobranca_id ? 'Editar carteira de cobrança' : 'Nova carteira de cobrança'}>
        {editando && <FormCarteira inicial={editando} onFechar={() => setEditando(null)} />}
      </Sheet>
    </div>
  )
}

function FormCarteira({ inicial, onFechar }: { inicial: Partial<CarteiraCobranca>; onFechar: () => void }) {
  const [c, setC] = useState<Partial<CarteiraCobranca>>(inicial)
  const [erros, setErros] = useState<Record<string, string>>({})
  const bancos = useBancosCnab()
  const salvar = useSalvarCarteira()
  const banco = bancos.data?.find(b => b.codigo === c.banco)
  const set = (k: keyof CarteiraCobranca, v: string | boolean) => setC(atual => ({ ...atual, [k]: v }))

  const enviar = () => {
    setErros({})
    salvar.mutate(c, { onSuccess: onFechar, onError: e => setErros(parseApiErrors(e)) })
  }
  const campo = (k: keyof CarteiraCobranca, rotulo: string, extra?: { dica?: string; max?: number }) => (
    <label className="block">
      <span style={labelStyle}>{rotulo}</span>
      <input style={inputStyle} value={String(c[k] ?? '')} maxLength={extra?.max} onChange={e => set(k, e.target.value)} />
      {extra?.dica && <span style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>{extra.dica}</span>}
      {erros[k] && <span style={{ fontSize: 12, color: 'var(--danger-ink)' }}>⚠ {erros[k]}</span>}
    </label>
  )

  return (
    <div className="flex flex-col gap-3 text-sm">
      {campo('nome', 'Nome', { dica: 'Como a carteira aparece para quem gera os boletos. Ex.: "Itaú — carteira 109".' })}
      <label className="block">
        <span style={labelStyle}>Banco</span>
        <select style={selectStyle} value={c.banco ?? ''} onChange={e => set('banco', e.target.value)}>
          <option value="" disabled>Escolha o banco…</option>
          {(bancos.data ?? []).map(b => <option key={b.codigo} value={b.codigo}>{b.codigo} — {b.nome}</option>)}
        </select>
        {erros.banco && <span style={{ fontSize: 12, color: 'var(--danger-ink)' }}>⚠ {erros.banco}</span>}
      </label>
      <label className="block">
        <span style={labelStyle}>Layout do arquivo</span>
        <select style={selectStyle} value={c.layout ?? '240'} onChange={e => set('layout', e.target.value)}>
          {(banco?.layouts ?? ['240']).map(l => <option key={l} value={l}>CNAB {l}</option>)}
        </select>
        {erros.layout && <span style={{ fontSize: 12, color: 'var(--danger-ink)' }}>⚠ {erros.layout}</span>}
      </label>
      <div className="grid grid-cols-4 gap-2">
        <div className="col-span-3">{campo('agencia', banco?.codigo === '748' || banco?.codigo === '756' ? 'Cooperativa' : 'Agência', { max: 5 })}</div>
        {campo('agencia_dv', 'DV', { max: 1 })}
        <div className="col-span-3">{campo('conta', 'Conta', { max: 12 })}</div>
        {campo('conta_dv', 'DV', { max: 2 })}
      </div>
      <div className="grid grid-cols-2 gap-2">
        {campo('carteira', 'Carteira', { max: 3 })}
        {campo('variacao_carteira', banco?.ajuda.variacao_carteira ?? 'Variação (se houver)', { max: 3 })}
      </div>
      {campo('convenio', banco?.ajuda.convenio ?? 'Convênio / código do beneficiário', { max: 20 })}
      {campo('beneficiario_nome', 'Razão social do beneficiário')}
      {/* Máscara só na tela; o estado e a API ficam com os dígitos (convenções §2). */}
      <label className="block">
        <span style={labelStyle}>CNPJ/CPF do beneficiário</span>
        <input
          style={inputStyle}
          inputMode="numeric"
          value={maskCPFCNPJ(c.beneficiario_documento ?? '')}
          onChange={e => {
            setErros(prev => ({ ...prev, beneficiario_documento: '' }))
            set('beneficiario_documento', e.target.value.replace(/\D/g, '').slice(0, 14))
          }}
          onBlur={() => {
            const erro = validateCPFCNPJ(c.beneficiario_documento ?? '')
            if (erro) setErros(prev => ({ ...prev, beneficiario_documento: erro }))
          }}
        />
        {erros.beneficiario_documento && <span style={{ fontSize: 12, color: 'var(--danger-ink)' }}>⚠ {erros.beneficiario_documento}</span>}
      </label>
      {campo('instrucoes', 'Instruções impressas no boleto', { dica: 'Ex.: "Não receber após 60 dias do vencimento."' })}
      {c.conta_cobranca_id && (
        <div className="grid grid-cols-2 gap-2">
          {campo('proximo_nosso_numero', 'Próximo nosso número', { dica: 'Mude só se o banco pedir — número repetido é recusado.' })}
          {campo('proximo_sequencial_remessa', 'Próxima remessa nº')}
        </div>
      )}
      <label className="flex items-center gap-2">
        <input type="checkbox" checked={c.ativa ?? true} onChange={e => set('ativa', e.target.checked)} /> Carteira ativa
      </label>
      <p style={{ fontSize: 12, color: 'var(--ink-3)' }}>
        Antes do primeiro uso, o banco confere uma remessa de teste da carteira (homologação). Gere um lote pequeno e envie como teste.
      </p>
      {erros._form && <p style={{ color: 'var(--danger-ink)' }}>⚠ {erros._form}</p>}
      <div className="flex justify-end gap-2">
        <button type="button" onClick={onFechar} style={buttonSecondaryStyle}>Cancelar</button>
        <button type="button" onClick={enviar} disabled={salvar.isPending} style={buttonPrimaryStyle}>{salvar.isPending ? 'Salvando…' : 'Salvar carteira'}</button>
      </div>
    </div>
  )
}

function EnviarRetorno({ carteiras }: { carteiras: CarteiraCobranca[] }) {
  const [carteira, setCarteira] = useState<number | ''>('')
  const [resultado, setResultado] = useState<RetornoCnab | null>(null)
  const [erro, setErro] = useState<string | null>(null)
  const arquivo = useRef<HTMLInputElement>(null)
  const enviar = useEnviarRetorno()
  const escolhida = carteira || carteiras[0]?.conta_cobranca_id

  const aoEscolher = (f: File | undefined) => {
    if (!f || !escolhida) return
    setErro(null)
    setResultado(null)
    enviar.mutate({ carteira: escolhida, arquivo: f }, {
      onSuccess: r => setResultado(r),
      onError: e => setErro(parseApiErrors(e)._form ?? 'Não foi possível ler o retorno.'),
    })
    if (arquivo.current) arquivo.current.value = ''
  }

  if (!carteiras.length) return null
  return (
    <Secao titulo="Enviar arquivo de retorno">
      <div className="flex items-center gap-3 flex-wrap">
        <select style={{ ...selectStyle, maxWidth: 320 }} value={escolhida ?? ''} onChange={e => setCarteira(Number(e.target.value))}>
          {carteiras.map(c => <option key={c.conta_cobranca_id} value={c.conta_cobranca_id}>{c.nome}</option>)}
        </select>
        <input ref={arquivo} type="file" accept=".ret,.RET,.txt,.TXT" hidden onChange={e => aoEscolher(e.target.files?.[0])} />
        <button type="button" onClick={() => arquivo.current?.click()} disabled={enviar.isPending} className="flex items-center gap-2" style={buttonSecondaryStyle}>
          <Upload size={15} /> {enviar.isPending ? 'Lendo o retorno…' : 'Escolher arquivo de retorno'}
        </button>
      </div>
      {erro && <p className="mt-2" style={{ color: 'var(--danger-ink)' }}>⚠ {erro}</p>}
      {resultado && <ResumoRetorno r={resultado} />}
    </Secao>
  )
}

function ResumoRetorno({ r }: { r: RetornoCnab }) {
  const s = r.resumo
  return (
    <div className="mt-3 text-sm" style={{ background: 'var(--surface-2)', borderRadius: 'var(--r-md)', padding: '10px 12px' }}>
      <strong style={{ color: 'var(--ink)' }}>{s.pagos} boleto{s.pagos !== 1 ? 's' : ''} pago{s.pagos !== 1 ? 's' : ''} — {formatBRL(apiDecimalToCents(s.valor_recebido))} baixados nas contas.</strong>
      <div style={{ fontSize: 12.5 }}>
        {s.registrados} registrado{s.registrados !== 1 ? 's' : ''} no banco · {s.rejeitados} recusado{s.rejeitados !== 1 ? 's' : ''} · {s.baixados} baixado{s.baixados !== 1 ? 's' : ''}
        {s.ja_processados > 0 && ` · ${s.ja_processados} já lido${s.ja_processados !== 1 ? 's' : ''} antes (sem nova baixa)`}
        {s.nao_encontrados > 0 && ` · ${s.nao_encontrados} não encontrado${s.nao_encontrados !== 1 ? 's' : ''} nesta carteira`}
        {s.em_revisao > 0 && ` · ${s.em_revisao} foram para a revisão de baixas`}
      </div>
    </div>
  )
}

/** Célula das tabelas de arquivos: respiro entre colunas, número alinhado por dígito. */
const cel = (extra?: CSSProperties): CSSProperties => ({ padding: '9px 12px', verticalAlign: 'middle', ...extra })
const num: CSSProperties = { textAlign: 'right', fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap' }
const cabecalho: CSSProperties = {
  padding: '0 12px 8px', textAlign: 'left', color: 'var(--ink-3)', fontSize: 11, fontWeight: 600,
  letterSpacing: '0.04em', textTransform: 'uppercase', whiteSpace: 'nowrap',
}

function TabelaRemessas({ remessas, carregando }: { remessas: RemessaCnab[]; carregando: boolean }) {
  const baixar = useBaixarRemessa()
  if (!remessas.length) return <p className="text-sm">{carregando ? 'Carregando…' : 'Nenhuma remessa ainda. Gere boletos pelo banco em Contas a receber.'}</p>
  return (
    <div style={{ overflowX: 'auto' }}>
      <table className="w-full text-sm" style={{ borderCollapse: 'collapse' }}>
        <thead>
          <tr>
            <th style={cabecalho}>Arquivo</th><th style={cabecalho}>Carteira</th>
            <th style={{ ...cabecalho, textAlign: 'right' }}>Boletos</th><th style={{ ...cabecalho, textAlign: 'right' }}>Valor</th>
            <th style={cabecalho}>Gerada em</th><th style={cabecalho} />
          </tr>
        </thead>
        <tbody>
          {remessas.map(r => (
            <tr key={r.remessa_id} style={{ borderTop: '1px solid var(--line-2)' }}>
              <td style={cel({ fontFamily: 'var(--mono)', whiteSpace: 'nowrap' })}>{r.nome_arquivo}</td>
              <td style={cel()}>{r.carteira_nome}</td>
              <td style={cel(num)}>{r.quantidade.toLocaleString('pt-BR')}</td>
              <td style={cel({ ...num, fontWeight: 600, color: 'var(--ink)' })}>{formatBRL(apiDecimalToCents(r.valor_total))}</td>
              <td style={cel({ whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums' })}>{dataHoraBR(r.criado_em)}</td>
              <td style={cel({ textAlign: 'right' })}>
                <button type="button" onClick={() => baixar.mutate(r)} className="flex items-center gap-1.5 ml-auto" style={{ ...buttonSecondaryStyle, padding: '4px 10px' }}>
                  <Download size={13} /> Baixar
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function TabelaRetornos({ retornos, carregando }: { retornos: RetornoCnab[]; carregando: boolean }) {
  if (!retornos.length) return <p className="text-sm">{carregando ? 'Carregando…' : 'Nenhum retorno enviado ainda.'}</p>
  return (
    <div style={{ overflowX: 'auto' }}>
      <table className="w-full text-sm" style={{ borderCollapse: 'collapse' }}>
        <thead>
          <tr>
            <th style={cabecalho}>Arquivo</th><th style={cabecalho}>Carteira</th>
            <th style={{ ...cabecalho, textAlign: 'right' }}>Pagos</th><th style={{ ...cabecalho, textAlign: 'right' }}>Recusados</th>
            <th style={{ ...cabecalho, textAlign: 'right' }}>Recebido</th><th style={cabecalho}>Enviado em</th>
          </tr>
        </thead>
        <tbody>
          {retornos.map(r => (
            <tr key={r.retorno_id} style={{ borderTop: '1px solid var(--line-2)' }}>
              <td style={cel({ fontFamily: 'var(--mono)', whiteSpace: 'nowrap' })}>{r.nome_arquivo}</td>
              <td style={cel()}>{r.carteira_nome}</td>
              <td style={cel(num)}>{r.resumo.pagos}</td>
              <td style={cel(num)}>{r.resumo.rejeitados}</td>
              <td style={cel({ ...num, fontWeight: 600, color: 'var(--ink)' })}>{formatBRL(apiDecimalToCents(r.resumo.valor_recebido))}</td>
              <td style={cel({ whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums' })}>{dataHoraBR(r.recebido_em)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Secao({ titulo, children }: { titulo: string; children: ReactNode }) {
  return (
    <section>
      <h2 className="text-xs font-semibold uppercase mb-2" style={{ color: 'var(--ink-3)', letterSpacing: '0.06em' }}>{titulo}</h2>
      {children}
    </section>
  )
}
