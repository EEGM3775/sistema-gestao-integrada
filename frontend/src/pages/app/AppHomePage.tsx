import { useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Activity, CalendarDays, LayoutDashboard, LayoutGrid, ListChecks } from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import { Quarteirao } from '@/components/brand/Quarteirao'
import { acessoDoModulo, CATALOGO } from './home/catalogo'
import { useHomeResumo } from './home/useHomeResumo'
import { TabVisaoGeral } from './home/TabVisaoGeral'
import { TabDecisoes } from './home/TabDecisoes'
import { TabAgenda } from './home/TabAgenda'
import { TabModulos } from './home/TabModulos'
import { TabAtividade } from './home/TabAtividade'

/**
 * Hub da Edição Construtora — o padrão de página da identidade §9:
 * faixa Meia-Noite com a malha viva (saudação + chip da edição + números vivos),
 * e o resto do conteúdo distribuído em **abas horizontais**.
 *
 * A escolha das abas segue o que as plataformas grandes convergiram a colocar na
 * home: um painel de indicadores, uma fila do que exige ação (*Assigned to Me* do
 * Autodesk Construction Cloud, *open items for review* do Procore, *Assistant* do
 * Salesforce), a agenda do dia (*Today's Tasks* do Salesforce, *today's schedule*
 * do Procore), o lançador de módulos (*App Launcher* do Salesforce, *spaces* do
 * SAP Fiori Launchpad) e o feed de mudanças recentes (*Recent Items*).
 *
 * A aba vive na URL (`?aba=`) — assim um link para "a fila de decisão" é
 * compartilhável e o botão voltar do navegador funciona.
 */

const ABAS = [
  { id: 'visao', label: 'Visão geral', icon: LayoutDashboard },
  { id: 'decisoes', label: 'Requer decisão', icon: ListChecks },
  { id: 'agenda', label: 'Agenda', icon: CalendarDays },
  { id: 'modulos', label: 'Módulos', icon: LayoutGrid },
  { id: 'atividade', label: 'Atividade', icon: Activity },
] as const

type AbaId = (typeof ABAS)[number]['id']

export default function AppHomePage() {
  const { user, hasModule, isTenantAdmin } = useAuth()
  const [params, setParams] = useSearchParams()
  const r = useHomeResumo()

  const abaAtual = (ABAS.find((a) => a.id === params.get('aba'))?.id ?? 'visao') as AbaId
  const irPara = (id: AbaId) => setParams(id === 'visao' ? {} : { aba: id }, { replace: true })

  const agora = new Date()
  const saudacao = agora.getHours() < 12 ? 'Bom dia' : agora.getHours() < 18 ? 'Boa tarde' : 'Boa noite'
  const dataLonga = agora.toLocaleDateString('pt-BR', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  })

  // Quantos módulos este usuário realmente abre — número honesto do farol.
  const disponiveis = useMemo(
    () => CATALOGO.filter((m) => acessoDoModulo(m, hasModule, isTenantAdmin).pode).length,
    [hasModule, isTenantAdmin],
  )

  const temFonteOperacional = r.fontes.erp || r.fontes.scm || r.fontes.sil

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100%' }}>
      {/* ── Faixa Meia-Noite com a malha viva (identidade §9) ─────────────── */}
      <header
        style={{
          position: 'relative',
          overflow: 'hidden',
          background: 'linear-gradient(135deg, var(--midnight) 0%, var(--midnight-2) 100%)',
          color: 'var(--on-midnight)',
          padding: '26px 28px 22px',
        }}
      >
        {/* A malha: o traçado de quarteirões que dá nome ao sistema. */}
        <div
          aria-hidden
          style={{
            position: 'absolute',
            inset: 0,
            opacity: 0.13,
            backgroundImage:
              'linear-gradient(var(--on-midnight-2) 1px, transparent 1px), linear-gradient(90deg, var(--on-midnight-2) 1px, transparent 1px)',
            backgroundSize: '44px 44px',
            maskImage: 'radial-gradient(120% 100% at 88% 0%, #000 10%, transparent 72%)',
            WebkitMaskImage: 'radial-gradient(120% 100% at 88% 0%, #000 10%, transparent 72%)',
          }}
        />

        <div style={{ position: 'relative', display: 'flex', alignItems: 'flex-start', gap: 16, flexWrap: 'wrap' }}>
          {/* Sobre o céu Meia-Noite o marco vai sem tile e com a praça em Papel (§9). */}
          <Quarteirao size={38} tile={null} praca="var(--on-midnight)" />

          <div style={{ minWidth: 0, flex: 1 }}>
            <h1
              style={{
                fontFamily: 'var(--display)',
                fontSize: 25,
                fontWeight: 800,
                letterSpacing: '-0.025em',
                color: 'var(--on-midnight)',
                lineHeight: 1.15,
              }}
            >
              {saudacao}, {user?.username ?? 'bem-vindo'}.
            </h1>
            <p style={{ fontSize: 12.5, color: 'var(--on-midnight-2)', marginTop: 4, textTransform: 'capitalize' }}>
              {dataLonga}
            </p>
          </div>

          {/* Chip da edição — toda tela declara seu endereço no ciclo (§9). */}
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 7,
              padding: '5px 11px',
              borderRadius: 999,
              background: 'color-mix(in srgb, var(--accent) 18%, transparent)',
              border: '1px solid color-mix(in srgb, var(--accent) 40%, transparent)',
              color: 'var(--accent)',
              fontSize: 11.5,
              fontWeight: 700,
              whiteSpace: 'nowrap',
            }}
          >
            <span style={{ width: 7, height: 7, borderRadius: 2, background: 'var(--accent)' }} />
            Edição Construtora · Construir
          </span>
        </div>

        {/* Números vivos — reais, e clicáveis para onde se resolve. */}
        <div style={{ position: 'relative', display: 'flex', gap: 26, marginTop: 18, flexWrap: 'wrap' }}>
          <NumeroVivo
            valor={r.decisoes.length}
            label={r.decisoes.length === 1 ? 'decisão aguardando' : 'decisões aguardando'}
            destaque={r.decisoes.length > 0}
            onClick={() => irPara('decisoes')}
          />
          <NumeroVivo
            valor={r.agenda.data?.length ?? 0}
            label="compromissos em 7 dias"
            onClick={() => irPara('agenda')}
          />
          <NumeroVivo valor={disponiveis} label="módulos disponíveis" onClick={() => irPara('modulos')} />
        </div>
      </header>

      {/* ── Abas horizontais ──────────────────────────────────────────────── */}
      <nav
        style={{
          display: 'flex',
          gap: 2,
          padding: '0 22px',
          borderBottom: '1px solid var(--line)',
          background: 'var(--surface)',
          overflowX: 'auto',
          position: 'sticky',
          top: 0,
          zIndex: 5,
        }}
      >
        {ABAS.map((a) => {
          const ativa = a.id === abaAtual
          const Icon = a.icon
          const contagem = a.id === 'decisoes' ? r.decisoes.length : 0
          return (
            <button
              key={a.id}
              onClick={() => irPara(a.id)}
              aria-current={ativa ? 'page' : undefined}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 7,
                padding: '13px 14px',
                fontSize: 13,
                fontWeight: ativa ? 650 : 500,
                color: ativa ? 'var(--ink)' : 'var(--ink-3)',
                background: 'transparent',
                border: 'none',
                borderBottom: `2px solid ${ativa ? 'var(--accent)' : 'transparent'}`,
                cursor: 'pointer',
                whiteSpace: 'nowrap',
                fontFamily: 'var(--sans)',
              }}
            >
              <Icon size={15} strokeWidth={1.9} />
              {a.label}
              {contagem > 0 && (
                <span
                  className="num"
                  style={{
                    background: 'var(--accent)',
                    color: '#1A1204',
                    borderRadius: 999,
                    padding: '1px 6px',
                    fontSize: 10.5,
                    fontWeight: 700,
                  }}
                >
                  {contagem}
                </span>
              )}
            </button>
          )
        })}
      </nav>

      {/* ── Conteúdo da aba ───────────────────────────────────────────────── */}
      <div style={{ padding: '22px 28px 40px', flex: 1 }}>
        {abaAtual === 'visao' && <TabVisaoGeral r={r} />}
        {abaAtual === 'decisoes' && <TabDecisoes decisoes={r.decisoes} temFonte={temFonteOperacional} />}
        {abaAtual === 'agenda' && (
          <TabAgenda eventos={r.agenda.data} carregando={r.agenda.isLoading} erro={r.agenda.isError} />
        )}
        {abaAtual === 'modulos' && <TabModulos />}
        {abaAtual === 'atividade' && (
          <TabAtividade fatos={r.atividade} temFonte={r.fontes.scm || r.fontes.sil} />
        )}
      </div>
    </div>
  )
}

function NumeroVivo({
  valor,
  label,
  destaque,
  onClick,
}: {
  valor: number
  label: string
  destaque?: boolean
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      style={{
        display: 'flex',
        alignItems: 'baseline',
        gap: 7,
        background: 'transparent',
        border: 'none',
        padding: 0,
        cursor: 'pointer',
        fontFamily: 'var(--sans)',
      }}
    >
      <span
        className="num"
        style={{
          fontSize: 20,
          fontWeight: 700,
          color: destaque ? 'var(--accent)' : 'var(--on-midnight)',
          letterSpacing: '-0.02em',
        }}
      >
        {valor}
      </span>
      <span style={{ fontSize: 12, color: 'var(--on-midnight-2)' }}>{label}</span>
    </button>
  )
}
