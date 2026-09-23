import { useMemo, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { Camera, ChevronLeft, Check, Lock, Undo2, X } from 'lucide-react'
import { Btn, Loading, Modal, Pill } from '@/components/malha'
import { useAuth } from '@/hooks/useAuth'
import { useFileUpload } from '@/hooks/useFileUpload'
import { dateToBR, maxCalendarioISO, minCalendarioISO } from '@/utils/dates'
import { parseApiErrors } from '@/utils/formErrors'
import { percentual } from '../formato'
import {
  useApontamentosDaSemana, useApontar, useEstornarApontamento, useMinhasFrentes,
} from '../hooks'
import { hojeIso, somaDias } from '../semana'
import { useCampo } from './contexto'
import type { ApontamentoAvanco } from '../types'

/** **Apontar avanço** — o ato que produz o número de que todo indicador acima
 *  depende, e o único da tela.
 *
 *  Uma decisão por tela, número grande, teclado numérico e a foto opcional. O
 *  valor é **quanto andou**, não quanto já está feito: é o que alguém responde
 *  olhando o serviço, e é a mesma régua do livro-razão do backend — corrigir
 *  não apaga, estorna. */
export default function ApontarPage() {
  const { atividadeId } = useParams()
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const { como } = useCampo()
  const { hasPermission } = useAuth()
  const { validate, acceptAttr } = useFileUpload()
  const podeApontar = hasPermission('pdca.avanco.apontar')

  const atividade = Number(atividadeId)
  const itemId = Number(params.get('item'))
  const localId = params.get('local') ? Number(params.get('local')) : null

  const frente = useMinhasFrentes({ como: como || undefined })
  const apontar = useApontar()
  const estornar = useEstornarApontamento()

  const [quanto, setQuanto] = useState('')
  const [data, setData] = useState(hojeIso())
  const [observacao, setObservacao] = useState('')
  const [foto, setFoto] = useState<File | null>(null)
  const [erro, setErro] = useState<string | null>(null)
  const [gravado, setGravado] = useState(false)
  const [estornando, setEstornando] = useState<ApontamentoAvanco | null>(null)

  const semana = frente.data
  const compromisso = useMemo(
    () => semana?.compromissos?.linhas.find(
      (l) => (itemId ? l.item === itemId : l.atividade === atividade),
    ),
    [semana, itemId, atividade],
  )

  const inicio = semana?.semana_inicio ?? somaDias(hojeIso(), -6)
  const fim = semana?.semana_fim ?? hojeIso()
  const lancamentos = useApontamentosDaSemana(atividade, inicio, fim)

  if (frente.isLoading) return <Loading o="o serviço" />

  if (!compromisso) {
    return (
      <div style={{ padding: 18, display: 'flex', flexDirection: 'column', gap: 14 }}>
        <p style={{ fontSize: 14, color: 'var(--ink-2)', lineHeight: 1.6, margin: 0 }}>
          Este serviço não está mais entre os que você assumiu nesta semana. Pode
          ter sido remanejado na reunião — volte à sua frente para ver o que está
          no seu nome agora.
        </p>
        <Link to="/campo" style={{ textDecoration: 'none' }}>
          <Btn variant="primary">Voltar à minha frente</Btn>
        </Link>
      </div>
    )
  }

  const jaApontado = Number(compromisso.apontado ?? 0)
  const prometido = compromisso.previsto == null ? null : Number(compromisso.previsto)
  const falta = prometido == null ? null : Math.max(prometido - jaApontado, 0)

  async function gravar() {
    setErro(null)
    const valor = quanto.trim().replace(',', '.')
    const numero = Number(valor)
    if (!valor || !Number.isFinite(numero) || numero <= 0) {
      setErro('Escreva quanto o serviço andou. Precisa ser um número maior que zero.')
      return
    }
    if (foto) {
      const problema = validate(foto)
      if (problema) {
        setErro(problema)
        return
      }
    }
    try {
      await apontar.mutateAsync({
        atividade,
        data,
        percentual: valor,
        local: localId,
        observacao,
        origem: 'app',
        foto,
      })
      setGravado(true)
      setQuanto('')
      setObservacao('')
      setFoto(null)
    } catch (e) {
      const erros = parseApiErrors(e)
      setErro(
        erros.percentual ?? erros._form ?? erros.detail
        ?? Object.values(erros)[0] ?? 'Não foi possível registrar.',
      )
    }
  }

  return (
    <div style={{ padding: '14px 14px 4px', display: 'flex', flexDirection: 'column', gap: 16 }}>
      <button
        type="button"
        onClick={() => navigate('/campo')}
        style={{
          display: 'inline-flex', alignItems: 'center', gap: 5, alignSelf: 'flex-start',
          minHeight: 44, padding: '0 4px', background: 'none', border: 'none',
          cursor: 'pointer', color: 'var(--ink-3)', fontSize: 13.5, fontFamily: 'inherit',
        }}
      >
        <ChevronLeft size={17} />
        Minha frente
      </button>

      <header>
        <h1
          style={{
            fontSize: 20, fontWeight: 750, color: 'var(--ink)', lineHeight: 1.3,
            margin: 0,
          }}
        >
          {compromisso.nome}
        </h1>
        <div style={{ fontSize: 13, color: 'var(--ink-3)', marginTop: 4 }}>
          {compromisso.obra_nome}
          {compromisso.local_rotulo && ` · ${compromisso.local_rotulo}`}
        </div>
        {(prometido != null || compromisso.apontou) && (
          <div style={{ display: 'flex', gap: 7, flexWrap: 'wrap', marginTop: 9 }}>
            {prometido != null && (
              <Pill kind="slate">assumiu {percentual(prometido)} nesta semana</Pill>
            )}
            {compromisso.apontou && (
              <Pill kind="good">já apontou {percentual(jaApontado)}</Pill>
            )}
            {falta != null && falta > 0 && (
              <Pill kind="accent">faltam {percentual(falta)}</Pill>
            )}
          </div>
        )}
      </header>

      {gravado && (
        <div
          role="status"
          style={{
            display: 'flex', alignItems: 'center', gap: 9, padding: '13px 14px',
            borderRadius: 'var(--r-md)', background: 'var(--good-soft)',
            color: 'var(--good-ink)', fontSize: 14, lineHeight: 1.5,
          }}
        >
          <Check size={19} style={{ flexShrink: 0 }} />
          Registrado. O escritório já está vendo.
        </div>
      )}

      {erro && (
        <div
          role="alert"
          style={{
            padding: '13px 14px', borderRadius: 'var(--r-md)',
            background: 'var(--danger-soft)', color: 'var(--danger-ink)',
            fontSize: 13.5, lineHeight: 1.55,
          }}
        >
          {erro}
        </div>
      )}

      {/* **Omitir × trancar**: o caminho existe para esta pessoa e o
          administrador pode liberá-lo, então o cadeado vem com o motivo em vez
          de um formulário que vai levar 403 no fim. */}
      {!podeApontar && (
        <div
          style={{
            display: 'flex', alignItems: 'flex-start', gap: 10,
            padding: '14px 15px', borderRadius: 'var(--r-md)',
            background: 'var(--inset)', border: '1px dashed var(--line)',
            fontSize: 13.5, color: 'var(--ink-2)', lineHeight: 1.6,
          }}
        >
          <Lock size={17} style={{ color: 'var(--ink-3)', flexShrink: 0, marginTop: 2 }} />
          <span>
            Você vê esta frente, mas não pode registrar avanço nela. Quem libera
            é o administrador da empresa — enquanto isso, avise o escritório.
          </span>
        </div>
      )}

      {podeApontar && (
      <section
        style={{
          background: 'var(--surface)', border: '1px solid var(--line)',
          borderRadius: 'var(--r-md)', padding: 16,
          display: 'flex', flexDirection: 'column', gap: 14,
          boxShadow: 'var(--shadow-sm)',
        }}
      >
        <label style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
          <span style={{ fontSize: 14, fontWeight: 650, color: 'var(--ink)' }}>
            Quanto o serviço andou
          </span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <input
              value={quanto}
              inputMode="decimal"
              autoFocus
              onChange={(e) => {
                setErro(null)
                setGravado(false)
                setQuanto(e.target.value.replace(/[^\d.,]/g, '').replace('.', ','))
              }}
              placeholder="0"
              aria-label="Quanto o serviço andou, em porcentagem"
              style={{
                flex: 1, minWidth: 0, padding: '14px 16px', borderRadius: 12,
                border: '1px solid var(--line)', background: 'var(--ground)',
                color: 'var(--ink)', fontSize: 38, fontWeight: 700,
                fontFamily: 'var(--mono)', textAlign: 'right',
              }}
            />
            <span
              style={{
                fontSize: 30, fontWeight: 700, color: 'var(--ink-3)', flexShrink: 0,
              }}
            >
              %
            </span>
          </div>
          <span style={{ fontSize: 12.5, color: 'var(--ink-3)', lineHeight: 1.5 }}>
            É o quanto andou <strong>hoje</strong>, não o total já feito. Se
            errar, dá para estornar aqui embaixo.
          </span>
        </label>

        <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <span style={{ fontSize: 13.5, fontWeight: 650, color: 'var(--ink)' }}>
            Em que dia
          </span>
          <input
            type="date"
            value={data}
            min={minCalendarioISO}
            max={maxCalendarioISO}
            onChange={(e) => setData(e.target.value)}
            style={{
              width: '100%', minHeight: 48, padding: '12px 13px', borderRadius: 10,
              border: '1px solid var(--line)', background: 'var(--surface)',
              color: 'var(--ink)', fontSize: 16, fontFamily: 'inherit',
            }}
          />
        </label>

        <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <span style={{ fontSize: 13.5, fontWeight: 650, color: 'var(--ink)' }}>
            Alguma observação
          </span>
          <textarea
            value={observacao}
            onChange={(e) => setObservacao(e.target.value)}
            rows={2}
            placeholder="Opcional"
            style={{
              width: '100%', padding: '12px 13px', borderRadius: 10, fontSize: 16,
              border: '1px solid var(--line)', background: 'var(--surface)',
              color: 'var(--ink)', fontFamily: 'inherit', resize: 'vertical',
            }}
          />
        </label>

        {/* A foto abre a câmera de trás direto — no canteiro, o que se quer
            fotografar é o serviço, e não escolher um arquivo. */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <label
            style={{
              display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
              gap: 8, minHeight: 48, padding: '0 16px', borderRadius: 10,
              border: '1px solid var(--line)', background: 'var(--surface-2)',
              color: 'var(--ink-2)', fontSize: 14.5, fontWeight: 650,
              cursor: 'pointer', flexShrink: 0,
            }}
          >
            <Camera size={18} />
            {foto ? 'Trocar foto' : 'Tirar foto'}
            <input
              type="file"
              accept={acceptAttr || 'image/*'}
              capture="environment"
              onChange={(e) => {
                setErro(null)
                setFoto(e.target.files?.[0] ?? null)
              }}
              style={{ display: 'none' }}
            />
          </label>
          {foto && (
            <button
              type="button"
              onClick={() => setFoto(null)}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 5, minHeight: 44,
                background: 'none', border: 'none', cursor: 'pointer',
                color: 'var(--ink-3)', fontSize: 13, fontFamily: 'inherit',
                minWidth: 0,
              }}
            >
              <X size={15} />
              <span
                style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
              >
                {foto.name}
              </span>
            </button>
          )}
        </div>

        <button
          type="button"
          onClick={gravar}
          disabled={apontar.isPending}
          style={{
            width: '100%', minHeight: 56, borderRadius: 12, border: 'none',
            background: 'var(--accent)', color: '#1A1204',
            fontSize: 17, fontWeight: 750, fontFamily: 'inherit',
            cursor: apontar.isPending ? 'wait' : 'pointer',
            opacity: apontar.isPending ? 0.6 : 1,
          }}
        >
          {apontar.isPending ? 'Registrando…' : 'Registrar avanço'}
        </button>
      </section>
      )}

      <LancamentosDaSemana
        lancamentos={lancamentos.data ?? []}
        carregando={lancamentos.isLoading}
        podeEstornar={podeApontar}
        aoEstornar={setEstornando}
      />

      {estornando && (
        <DialogoDeEstorno
          lancamento={estornando}
          salvando={estornar.isPending}
          aoFechar={() => setEstornando(null)}
          aoConfirmar={async (motivo) => {
            await estornar.mutateAsync({ id: estornando.apontamento_id, motivo })
            setEstornando(null)
          }}
        />
      )}
    </div>
  )
}

/** **O que eu apontei nesta semana** — e o estorno a um toque.
 *
 *  A linha errada não some: o estorno aponta para ela e a soma dá o número
 *  certo. É a mesma regra do livro-razão, e é o que permite ao campo corrigir o
 *  próprio erro sem pedir nada a ninguém. */
function LancamentosDaSemana({
  lancamentos, carregando, podeEstornar, aoEstornar,
}: {
  lancamentos: ApontamentoAvanco[]
  carregando: boolean
  podeEstornar: boolean
  aoEstornar: (lancamento: ApontamentoAvanco) => void
}) {
  if (carregando) {
    return (
      <p style={{ fontSize: 13, color: 'var(--ink-3)', padding: '0 2px' }}>
        Carregando o que já foi apontado…
      </p>
    )
  }
  if (lancamentos.length === 0) return null

  return (
    <section>
      <div
        style={{
          fontSize: 11, letterSpacing: '0.12em', textTransform: 'uppercase',
          color: 'var(--ink-3)', fontWeight: 700, marginBottom: 9,
        }}
      >
        Apontado nesta semana
      </div>
      <div
        style={{
          background: 'var(--surface)', border: '1px solid var(--line)',
          borderRadius: 'var(--r-md)', overflow: 'hidden',
        }}
      >
        {lancamentos.map((lancamento) => {
          const negativo = Number(lancamento.percentual) < 0
          return (
            <div
              key={lancamento.apontamento_id}
              style={{
                display: 'flex', alignItems: 'center', gap: 11,
                padding: '11px 13px', borderTop: '1px solid var(--line-2)',
                opacity: lancamento.estornado ? 0.55 : 1,
              }}
            >
              <span
                className="num"
                style={{
                  fontSize: 15, fontWeight: 700, minWidth: 66, textAlign: 'right',
                  color: negativo ? 'var(--danger-ink)' : 'var(--ink)',
                  textDecoration: lancamento.estornado ? 'line-through' : 'none',
                }}
              >
                {negativo ? '' : '+'}{percentual(lancamento.percentual, 2)}
              </span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 12.5, color: 'var(--ink-2)' }}>
                  {dateToBR(lancamento.data)}
                  {lancamento.apontado_por && ` · ${lancamento.apontado_por}`}
                </div>
                {lancamento.observacao && (
                  <div
                    style={{
                      fontSize: 11.5, color: 'var(--ink-3)', marginTop: 2,
                      overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                    }}
                  >
                    {lancamento.observacao}
                  </div>
                )}
              </div>
              {podeEstornar && !lancamento.estornado && !negativo && (
                <button
                  type="button"
                  onClick={() => aoEstornar(lancamento)}
                  aria-label="Estornar este apontamento"
                  title="Estornar este apontamento"
                  style={{
                    display: 'grid', placeItems: 'center', width: 44, height: 44,
                    flexShrink: 0, borderRadius: 10, cursor: 'pointer',
                    background: 'var(--surface-2)', border: '1px solid var(--line)',
                    color: 'var(--ink-2)',
                  }}
                >
                  <Undo2 size={17} />
                </button>
              )}
            </div>
          )
        })}
      </div>
    </section>
  )
}

function DialogoDeEstorno({
  lancamento, salvando, aoFechar, aoConfirmar,
}: {
  lancamento: ApontamentoAvanco
  salvando: boolean
  aoFechar: () => void
  aoConfirmar: (motivo: string) => Promise<void>
}) {
  const [motivo, setMotivo] = useState('')
  const [erro, setErro] = useState<string | null>(null)

  async function confirmar() {
    setErro(null)
    try {
      await aoConfirmar(motivo)
    } catch (e) {
      const erros = parseApiErrors(e)
      setErro(erros.motivo ?? erros._form ?? erros.detail ?? 'Não foi possível estornar.')
    }
  }

  return (
    <Modal
      titulo="Estornar o apontamento"
      onClose={aoFechar}
      largura={430}
      rodape={
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <Btn onClick={aoFechar}>Cancelar</Btn>
          <Btn variant="primary" onClick={confirmar} disabled={salvando}>
            {salvando ? 'Estornando…' : 'Estornar'}
          </Btn>
        </div>
      }
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 13 }}>
        {erro && (
          <div
            role="alert"
            style={{
              fontSize: 13, padding: '11px 13px', borderRadius: 'var(--r-sm)',
              background: 'var(--danger-soft)', color: 'var(--danger-ink)',
              lineHeight: 1.5,
            }}
          >
            {erro}
          </div>
        )}

        <p style={{ fontSize: 13.5, color: 'var(--ink-2)', lineHeight: 1.6, margin: 0 }}>
          O lançamento de{' '}
          <strong className="num">{percentual(lancamento.percentual, 2)}</strong>
          {' '}em {dateToBR(lancamento.data)} continua na lista, riscado, e um
          lançamento contrário entra no lugar. A soma passa a dar o número certo.
        </p>

        <textarea
          value={motivo}
          onChange={(e) => { setMotivo(e.target.value); setErro(null) }}
          rows={2}
          autoFocus
          placeholder="Ex.: digitei 50 no lugar de 5"
          style={{
            width: '100%', padding: '12px 13px', borderRadius: 10, fontSize: 16,
            border: '1px solid var(--line)', background: 'var(--surface)',
            color: 'var(--ink)', fontFamily: 'inherit', resize: 'vertical',
          }}
        />
      </div>
    </Modal>
  )
}
