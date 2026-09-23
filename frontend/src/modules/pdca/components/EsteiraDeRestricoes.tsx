import { useMemo, useState } from 'react'
import { AlertTriangle, Link2, Lock, Plus, ShoppingCart, Unlock } from 'lucide-react'
import { Btn, Card, Empty, Modal, Pill } from '@/components/malha'
import { useAuth } from '@/hooks/useAuth'
import { dateToBR, maxCalendarioISO, minCalendarioISO } from '@/utils/dates'
import { FieldError, FormErrorBanner, parseApiErrors, type FieldErrors } from '@/utils/formErrors'
import { contemSemAcento } from '@/utils/texto'
import { usePdca } from '../contexto'
import {
  useCriarRestricao, useGerarDemandaDeCompra, useRemoverRestricao,
} from '../hooks'
import { emDias } from '../formato'
import type { Atividade, Restricao, TipoRestricao } from '../types'

/** As oito famílias do *make-ready*. Rótulo e ordem são de quem está na
 *  reunião — o servidor manda `tipo_rotulo`, e isto aqui só ordena a escolha. */
const TIPOS: { codigo: TipoRestricao; rotulo: string }[] = [
  { codigo: 'material', rotulo: 'Material' },
  { codigo: 'projeto', rotulo: 'Projeto' },
  { codigo: 'mao_de_obra', rotulo: 'Mão de obra' },
  { codigo: 'equipamento', rotulo: 'Equipamento' },
  { codigo: 'area', rotulo: 'Área / frente anterior' },
  { codigo: 'licenca', rotulo: 'Licença / liberação' },
  { codigo: 'decisao', rotulo: 'Decisão do cliente' },
  { codigo: 'clima', rotulo: 'Clima' },
]

/** **A esteira do make-ready** — o que trava, quem resolve, quando vence.
 *
 *  Fica à esquerda do quadro porque é a pergunta que vem **antes** dele: a
 *  atividade com trava aberta não entra na semana, e descobrir isso ao tentar
 *  puxar o cartão é tarde demais para a reunião. */
export function EsteiraDeRestricoes({
  restricoes, atividades, carregando,
}: {
  restricoes: Restricao[]
  atividades: Atividade[]
  carregando: boolean
}) {
  const { obraId } = usePdca()
  const { hasPermission } = useAuth()
  const [abrindo, setAbrindo] = useState(false)
  const [removendo, setRemovendo] = useState<Restricao | null>(null)
  const [comprando, setComprando] = useState<Restricao | null>(null)

  const podeRegistrar = hasPermission('pdca.restricao.edit')
  const podeRemover = hasPermission('pdca.restricao.remover')
  const podeComprar = hasPermission('scm.demanda.edit')

  const vencidas = restricoes.filter((r) => (r.dias_para_o_prazo ?? 1) < 0).length

  return (
    <section
      style={{
        display: 'flex', flexDirection: 'column', minHeight: 0,
        width: 306, flexShrink: 0, borderRight: '1px solid var(--line)',
        background: 'var(--surface)',
      }}
    >
      <header
        style={{
          display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0,
          padding: '11px 13px', borderBottom: '1px solid var(--line-2)',
        }}
      >
        <div style={{ minWidth: 0, flex: 1 }}>
          <div
            style={{
              fontSize: 10.5, letterSpacing: '0.12em', textTransform: 'uppercase',
              color: 'var(--ink-3)', fontWeight: 700,
            }}
          >
            O que trava
          </div>
          <div style={{ fontSize: 11.5, color: 'var(--ink-3)', marginTop: 2 }}>
            {restricoes.length === 0
              ? 'nada aberto'
              : `${restricoes.length} aberta${restricoes.length > 1 ? 's' : ''}`}
            {vencidas > 0 && ` · ${vencidas} vencida${vencidas > 1 ? 's' : ''}`}
          </div>
        </div>
        {podeRegistrar && (
          <Btn tam="sm" onClick={() => setAbrindo(true)} title="Registrar uma trava">
            <Plus size={13} />
            Registrar
          </Btn>
        )}
      </header>

      <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: 10 }}>
        {carregando ? (
          <p style={{ fontSize: 12.5, color: 'var(--ink-3)', padding: 8 }}>
            Carregando o que trava a obra…
          </p>
        ) : restricoes.length === 0 ? (
          <Empty>
            <span style={{ lineHeight: 1.55 }}>
              Nenhum serviço está travado. É assim que a semana deveria começar —
              o quadro aceita qualquer frente do plano.
            </span>
            {podeRegistrar && (
              <Btn tam="sm" onClick={() => setAbrindo(true)}>
                <Plus size={13} />
                Registrar uma trava
              </Btn>
            )}
          </Empty>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {restricoes.map((restricao) => (
              <CartaoDeTrava
                key={restricao.restricao_id}
                restricao={restricao}
                podeRemover={podeRemover}
                podeComprar={podeComprar}
                aoRemover={() => setRemovendo(restricao)}
                aoComprar={() => setComprando(restricao)}
              />
            ))}
          </div>
        )}
      </div>

      {abrindo && (
        <DialogoDeTrava
          obraId={obraId}
          atividades={atividades}
          aoFechar={() => setAbrindo(false)}
        />
      )}
      {removendo && (
        <DialogoDeRemocao
          obraId={obraId}
          restricao={removendo}
          aoFechar={() => setRemovendo(null)}
        />
      )}
      {comprando && (
        <DialogoDeDemanda
          obraId={obraId}
          restricao={comprando}
          aoFechar={() => setComprando(null)}
        />
      )}
    </section>
  )
}

function CartaoDeTrava({
  restricao, podeRemover, podeComprar, aoRemover, aoComprar,
}: {
  restricao: Restricao
  podeRemover: boolean
  podeComprar: boolean
  aoRemover: () => void
  aoComprar: () => void
}) {
  const { selecionar } = usePdca()
  const dias = restricao.dias_para_o_prazo
  const jaComprou = restricao.demanda_scm != null

  return (
    <Card pad={false} style={{ overflow: 'hidden' }}>
      <button
        type="button"
        onClick={() => selecionar({ tipo: 'atividade', id: restricao.atividade })}
        title="Ver a atividade travada"
        style={{
          display: 'block', width: '100%', textAlign: 'left', cursor: 'pointer',
          background: 'none', border: 'none', padding: '10px 12px 8px', color: 'inherit',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
          <Pill kind="slate">{restricao.tipo_rotulo}</Pill>
          <SeloDePrazo dias={dias} prazo={restricao.prazo} />
        </div>
        <div
          style={{
            fontSize: 12.5, color: 'var(--ink)', lineHeight: 1.45, marginTop: 7,
          }}
        >
          {restricao.descricao}
        </div>
        <div
          style={{
            fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--ink-3)',
            marginTop: 5, overflow: 'hidden', textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {restricao.atividade_codigo} · {restricao.atividade_nome}
          {restricao.local_rotulo && ` · ${restricao.local_rotulo}`}
        </div>
        {restricao.responsavel && (
          <div style={{ fontSize: 11.5, color: 'var(--ink-3)', marginTop: 3 }}>
            com {restricao.responsavel}
          </div>
        )}
      </button>

      <div
        style={{
          display: 'flex', alignItems: 'center', gap: 6, padding: '7px 10px',
          borderTop: '1px solid var(--line-2)', background: 'var(--inset)',
        }}
      >
        {jaComprou ? (
          <span
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 4,
              fontSize: 11, color: 'var(--ink-3)',
            }}
            title="Esta trava já virou uma demanda no Suprimentos"
          >
            <Link2 size={11} />
            compra aberta
            {restricao.demanda_scm_status && ` · ${restricao.demanda_scm_status}`}
          </span>
        ) : restricao.tipo === 'material' && podeComprar ? (
          <button
            type="button"
            onClick={aoComprar}
            style={acaoDeRodape}
            title="Abrir a demanda de compra no Suprimentos"
          >
            <ShoppingCart size={11} />
            Pedir compra
          </button>
        ) : null}

        <span style={{ flex: 1 }} />

        {podeRemover ? (
          <button type="button" onClick={aoRemover} style={acaoDeRodape}>
            <Unlock size={11} />
            Destravar
          </button>
        ) : (
          <span
            style={{ ...acaoDeRodape, cursor: 'not-allowed', opacity: 0.6 }}
            title="Destravar exige a permissão “pdca.restricao.remover”. Peça ao administrador da empresa."
          >
            <Lock size={11} />
            Destravar
          </span>
        )}
      </div>
    </Card>
  )
}

const acaoDeRodape: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: 4,
  background: 'transparent', border: 'none', padding: 0, cursor: 'pointer',
  fontSize: 11.5, fontWeight: 650, color: 'var(--ink-2)',
}

/** O prazo, dito em dias. "Vencida" sozinha não distingue o atraso de ontem do
 *  de dois meses — e é a diferença que decide qual destravar primeiro. */
function SeloDePrazo({ dias, prazo }: { dias: number | null; prazo: string | null }) {
  if (prazo == null) {
    return (
      <span style={{ fontSize: 11, color: 'var(--ink-3)', fontStyle: 'italic' }}>
        sem prazo
      </span>
    )
  }
  if (dias == null) return null
  const texto = dias < 0
    ? `${emDias(dias)} em atraso`
    : dias === 0 ? 'vence hoje' : `faltam ${emDias(dias)}`
  return (
    <Pill kind={dias < 0 ? 'danger' : dias <= 2 ? 'accent' : 'slate'} title={dateToBR(prazo)}>
      {dias < 0 && <AlertTriangle size={11} />}
      {texto}
    </Pill>
  )
}

/* -------------------------------------------------------------------------- */

function DialogoDeTrava({
  obraId, atividades, aoFechar,
}: { obraId: number; atividades: Atividade[]; aoFechar: () => void }) {
  const criar = useCriarRestricao(obraId)
  const [erros, setErros] = useState<FieldErrors>({})
  const [busca, setBusca] = useState('')
  const [form, setForm] = useState({
    atividade: '', tipo: 'material' as TipoRestricao,
    descricao: '', responsavel: '', prazo: '',
  })

  /** Só folha: a sintética é o intervalo dos filhos, e travar a soma não
   *  travaria serviço nenhum — é a mesma recusa que o apontamento faz. */
  const folhas = useMemo(
    () => atividades.filter((a) => !a.tem_filhos && !a.eh_marco),
    [atividades],
  )
  const visiveis = useMemo(() => {
    if (!busca.trim()) return folhas.slice(0, 40)
    return folhas
      .filter((a) => contemSemAcento(`${a.codigo} ${a.nome}`, busca))
      .slice(0, 40)
  }, [folhas, busca])

  async function salvar() {
    setErros({})
    if (!form.atividade) {
      setErros({ atividade: 'Escolha o serviço que está travado.' })
      return
    }
    try {
      await criar.mutateAsync({
        atividade: Number(form.atividade),
        tipo: form.tipo,
        descricao: form.descricao,
        responsavel: form.responsavel,
        prazo: form.prazo || null,
      })
      aoFechar()
    } catch (e) {
      setErros(parseApiErrors(e))
    }
  }

  return (
    <Modal
      titulo="Registrar o que está travando"
      onClose={aoFechar}
      largura={560}
      rodape={
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <Btn onClick={aoFechar}>Cancelar</Btn>
          <Btn variant="primary" onClick={salvar} disabled={criar.isPending}>
            {criar.isPending ? 'Registrando…' : 'Registrar'}
          </Btn>
        </div>
      }
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 13 }}>
        <FormErrorBanner errors={erros} />

        <p style={{ fontSize: 12.5, color: 'var(--ink-2)', lineHeight: 1.55, margin: 0 }}>
          Enquanto a trava estiver aberta, este serviço não entra no quadro da
          semana — é o que impede o time de assumir o que já se sabe impedido.
        </p>

        <Campo rotulo="Serviço travado">
          <input
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
            placeholder="Procure pelo código ou pelo nome"
            style={entrada}
          />
          <select
            value={form.atividade}
            onChange={(e) => {
              setForm((f) => ({ ...f, atividade: e.target.value }))
              setErros((p) => ({ ...p, atividade: '' }))
            }}
            size={6}
            style={{ ...entrada, marginTop: 6, height: 'auto', padding: 4 }}
          >
            {visiveis.map((a) => (
              <option key={a.atividade_id} value={a.atividade_id}>
                {a.codigo} · {a.nome}
              </option>
            ))}
          </select>
          {folhas.length === 0 && (
            <span style={{ fontSize: 11.5, color: 'var(--ink-3)' }}>
              O plano desta obra ainda não tem serviço para travar.
            </span>
          )}
          <FieldError msg={erros.atividade} />
        </Campo>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <Campo rotulo="Que tipo de trava é">
            <select
              value={form.tipo}
              onChange={(e) => setForm((f) => ({ ...f, tipo: e.target.value as TipoRestricao }))}
              style={entrada}
            >
              {TIPOS.map((t) => (
                <option key={t.codigo} value={t.codigo}>{t.rotulo}</option>
              ))}
            </select>
            <FieldError msg={erros.tipo} />
          </Campo>

          <Campo rotulo="Quando precisa estar resolvida">
            <input
              type="date"
              value={form.prazo}
              min={minCalendarioISO}
              max={maxCalendarioISO}
              onChange={(e) => setForm((f) => ({ ...f, prazo: e.target.value }))}
              style={entrada}
            />
            <span style={{ fontSize: 11, color: 'var(--ink-3)' }}>
              Pode ficar em branco — nem toda trava tem data ainda.
            </span>
            <FieldError msg={erros.prazo} />
          </Campo>
        </div>

        <Campo rotulo="O que exatamente está faltando">
          <textarea
            value={form.descricao}
            onChange={(e) => {
              setForm((f) => ({ ...f, descricao: e.target.value }))
              setErros((p) => ({ ...p, descricao: '' }))
            }}
            rows={3}
            placeholder="Ex.: bloco cerâmico do 4º pavimento não entregue"
            style={{ ...entrada, resize: 'vertical' }}
          />
          <FieldError msg={erros.descricao} />
        </Campo>

        <Campo rotulo="Quem resolve">
          <input
            value={form.responsavel}
            onChange={(e) => setForm((f) => ({ ...f, responsavel: e.target.value }))}
            placeholder="Ex.: Suprimentos · projetista · fiscal da prefeitura"
            style={entrada}
          />
          <span style={{ fontSize: 11, color: 'var(--ink-3)' }}>
            Escreva o nome como ele aparece para a obra. Quem responde por
            destravar muitas vezes é de fora da empresa.
          </span>
          <FieldError msg={erros.responsavel} />
        </Campo>
      </div>
    </Modal>
  )
}

function DialogoDeRemocao({
  obraId, restricao, aoFechar,
}: { obraId: number; restricao: Restricao; aoFechar: () => void }) {
  const remover = useRemoverRestricao(obraId)
  const [nota, setNota] = useState('')
  const [erros, setErros] = useState<FieldErrors>({})

  async function confirmar() {
    setErros({})
    try {
      await remover.mutateAsync({ id: restricao.restricao_id, nota })
      aoFechar()
    } catch (e) {
      setErros(parseApiErrors(e))
    }
  }

  return (
    <Modal
      titulo="Destravar o serviço"
      onClose={aoFechar}
      largura={480}
      rodape={
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <Btn onClick={aoFechar}>Cancelar</Btn>
          <Btn variant="primary" onClick={confirmar} disabled={remover.isPending}>
            {remover.isPending ? 'Destravando…' : 'Destravar'}
          </Btn>
        </div>
      }
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 13 }}>
        <FormErrorBanner errors={erros} />

        <div
          style={{
            fontSize: 12.5, color: 'var(--ink-2)', lineHeight: 1.5,
            background: 'var(--inset)', borderRadius: 'var(--r-sm)', padding: '9px 11px',
          }}
        >
          <strong style={{ color: 'var(--ink)' }}>{restricao.tipo_rotulo}</strong>
          {' · '}{restricao.descricao}
        </div>

        <Campo rotulo="Como foi resolvida">
          <textarea
            value={nota}
            onChange={(e) => {
              setNota(e.target.value)
              setErros((p) => ({ ...p, nota: '' }))
            }}
            rows={3}
            autoFocus
            placeholder="Ex.: material entregue no canteiro hoje, conferido pelo almoxarife"
            style={{ ...entrada, resize: 'vertical' }}
          />
          <span style={{ fontSize: 11.5, color: 'var(--ink-3)', lineHeight: 1.5 }}>
            É o que a reunião da semana que vem lê para saber se ela foi
            resolvida ou apenas esquecida.
          </span>
          <FieldError msg={erros.nota} />
        </Campo>
      </div>
    </Modal>
  )
}

function DialogoDeDemanda({
  obraId, restricao, aoFechar,
}: { obraId: number; restricao: Restricao; aoFechar: () => void }) {
  const gerar = useGerarDemandaDeCompra(obraId)
  const [form, setForm] = useState({ quantidade: '', unidade: '' })
  const [erros, setErros] = useState<FieldErrors>({})

  async function confirmar() {
    setErros({})
    try {
      await gerar.mutateAsync({
        id: restricao.restricao_id,
        quantidade: form.quantidade.trim().replace(',', '.') || null,
        unidade: form.unidade,
      })
      aoFechar()
    } catch (e) {
      setErros(parseApiErrors(e))
    }
  }

  return (
    <Modal
      titulo="Pedir a compra no Suprimentos"
      onClose={aoFechar}
      largura={460}
      rodape={
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <Btn onClick={aoFechar}>Cancelar</Btn>
          <Btn variant="primary" onClick={confirmar} disabled={gerar.isPending}>
            {gerar.isPending ? 'Abrindo…' : 'Abrir a demanda'}
          </Btn>
        </div>
      }
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 13 }}>
        <FormErrorBanner errors={erros} />

        <p style={{ fontSize: 12.5, color: 'var(--ink-2)', lineHeight: 1.55, margin: 0 }}>
          Abre um documento no Suprimentos com o que está faltando. A trava
          continua aberta até alguém dizer que o material chegou — e o cartão
          passa a mostrar em que pé está a compra.
        </p>

        <div
          style={{
            fontSize: 12.5, color: 'var(--ink-2)', lineHeight: 1.5,
            background: 'var(--inset)', borderRadius: 'var(--r-sm)', padding: '9px 11px',
          }}
        >
          {restricao.descricao}
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <Campo rotulo="Quantidade">
            <input
              value={form.quantidade}
              inputMode="decimal"
              onChange={(e) => setForm((f) => ({ ...f, quantidade: e.target.value }))}
              placeholder="opcional"
              style={{ ...entrada, textAlign: 'right', fontFamily: 'var(--mono)' }}
            />
            <FieldError msg={erros.quantidade} />
          </Campo>
          <Campo rotulo="Unidade">
            <input
              value={form.unidade}
              onChange={(e) => setForm((f) => ({ ...f, unidade: e.target.value }))}
              placeholder="m², sc, un"
              style={entrada}
            />
            <FieldError msg={erros.unidade} />
          </Campo>
        </div>
      </div>
    </Modal>
  )
}

/* -------------------------------------------------------------------------- */

const entrada: React.CSSProperties = {
  width: '100%', padding: '8px 10px', borderRadius: 8,
  border: '1px solid var(--line)', background: 'var(--surface)',
  color: 'var(--ink)', fontSize: 13.5, fontFamily: 'inherit',
}

function Campo({ rotulo, children }: { rotulo: string; children: React.ReactNode }) {
  return (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
      <span
        style={{
          fontSize: 10.5, letterSpacing: '0.09em', textTransform: 'uppercase',
          color: 'var(--ink-3)', fontWeight: 700,
        }}
      >
        {rotulo}
      </span>
      {children}
    </label>
  )
}
