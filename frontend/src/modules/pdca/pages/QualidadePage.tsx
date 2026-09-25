import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { AlertTriangle, BookOpen, ClipboardCheck, RefreshCcw } from 'lucide-react'
import { Card, Empty, Loading } from '@/components/malha'
import { useAuth } from '@/hooks/useAuth'
import { usePdca } from '../contexto'
import { usePostoDaQualidade } from '../hooks'
import { BibliotecaDeModelos } from '../components/BibliotecaDeModelos'
import { DocumentoDaNc } from '../components/DocumentoDaNc'
import { FichaAplicada } from '../components/FichaAplicada'
import { FilaDeDecisao } from '../components/FilaDeDecisao'
import { FormularioDeNc } from '../components/FormularioDeNc'
import { ListaDeFichas } from '../components/ListaDeFichas'
import { ListaDeNcs } from '../components/ListaDeNcs'
import { PainelDeConformidade } from '../components/PainelDeConformidade'
import { SemPermissaoAviso } from '../components/SemPermissaoAviso'
import { VistasDoPosto, type VistaDoPosto } from '../components/VistasDoPosto'

type Vista = 'laco' | 'defeitos' | 'fichas' | 'modelos'

const VISTAS: VistaDoPosto<Vista>[] = [
  { chave: 'laco', rotulo: 'O laço aberto', icone: RefreshCcw },
  { chave: 'defeitos', rotulo: 'Defeitos', icone: AlertTriangle },
  { chave: 'fichas', rotulo: 'Fichas', icone: ClipboardCheck },
  { chave: 'modelos', rotulo: 'Modelos de ficha', icone: BookOpen },
]

/** A vista sai do endereço — e o documento aberto também. Quem tem `?nc=`
 *  cai nos defeitos, quem tem `?ficha=` nas fichas: o link colado abre onde
 *  o outro estava. */
function vistaDoEndereco(params: URLSearchParams): Vista {
  const pedida = params.get('v')
  if (pedida && VISTAS.some((v) => v.chave === pedida)) return pedida as Vista
  if (params.get('nc')) return 'defeitos'
  if (params.get('ficha')) return 'fichas'
  if (params.get('modelo')) return 'modelos'
  return 'laco'
}

/** **QUALIDADE** — o que reprovou, quem está tratando, e acabou mesmo?
 *
 *  Abre pelo laço aberto: a fila do posto (que é a do degrau de retrabalho da
 *  fila do dia, recortada) ao lado do que mais reprova. Dentro, três vistas
 *  sobre o mesmo laço — o defeito com o plano e a eficácia na mesma página, a
 *  ficha com a resposta ali mesmo, e a biblioteca de modelos, que é
 *  configuração e por isso mora aqui, sem item de menu. */
export default function QualidadePage() {
  const { obraId } = usePdca()
  const { hasPermission } = useAuth()
  const [params, setParams] = useSearchParams()
  const [registrando, setRegistrando] = useState(false)
  const posto = usePostoDaQualidade(obraId)

  const vista = vistaDoEndereco(params)
  const ncId = Number(params.get('nc')) || null
  const fichaId = Number(params.get('ficha')) || null
  const modeloId = Number(params.get('modelo')) || null

  const podeVerNc = hasPermission('pdca.nc.view')
  const podeAbrirNc = hasPermission('pdca.nc.abrir')
  const podeAplicar = hasPermission('pdca.verificacao.aplicar')

  /** Uma escrita só no endereço: vista e documento saem juntos, senão duas
   *  chamadas seguidas partiriam do mesmo `params` e a segunda desfaria a
   *  primeira. */
  function ir(qual: Vista, doc?: { nc?: number; ficha?: number; modelo?: number }) {
    const novo = new URLSearchParams()
    novo.set('v', qual)
    if (doc?.nc) novo.set('nc', String(doc.nc))
    if (doc?.ficha) novo.set('ficha', String(doc.ficha))
    if (doc?.modelo) novo.set('modelo', String(doc.modelo))
    setParams(novo)
  }

  if (posto.isLoading) return <Loading o="a qualidade da obra" />
  if (posto.isError || !posto.data) {
    return (
      <div style={{ padding: 26 }}>
        <Card>
          <Empty>
            Não foi possível carregar a qualidade desta obra. Verifique a conexão e
            tente de novo — nada do que estava aqui se perdeu.
          </Empty>
        </Card>
      </div>
    )
  }

  const dados = posto.data

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      <VistasDoPosto
        titulo="Qualidade"
        sub="contínua · disparada por evento"
        vistas={VISTAS}
        atual={vista}
        aoEscolher={(v) => ir(v)}
        contagem={{ laco: dados.fila.total || undefined }}
      />

      <div style={{ flex: 1, minHeight: 0, overflow: 'auto' }}>
        <div style={{ padding: '18px 20px 34px', maxWidth: 1240 }}>
          {vista === 'laco' && (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(420px, 1fr))', gap: 24, alignItems: 'start' }}>
              <FilaDeDecisao
                fila={dados.fila}
                obraId={obraId}
                titulo="O laço aberto"
                noPosto
                vazio={
                  <>
                    <strong style={{ color: 'var(--ink-2)' }}>Nenhum defeito parado nesta obra.</strong>
                    <br />
                    Nenhum sem plano, nenhuma ação vencida, nenhum conserto esperando
                    conferência e nenhuma ficha largada no meio.
                  </>
                }
              />
              {dados.painel ? (
                <PainelDeConformidade painel={dados.painel} />
              ) : (
                <SemPermissaoAviso itens={dados.sem_permissao} />
              )}
            </div>
          )}

          {vista === 'defeitos' && (
            !podeVerNc ? (
              <SemPermissaoAviso
                itens={dados.sem_permissao.filter((s) => s.permissao === 'pdca.nc.view')}
              />
            ) : ncId ? (
              <DocumentoDaNc ncId={ncId} obraId={obraId} aoVoltar={() => ir('defeitos')} />
            ) : (
              <ListaDeNcs
                obraId={obraId}
                aoAbrir={(id) => ir('defeitos', { nc: id })}
                aoRegistrar={podeAbrirNc ? () => setRegistrando(true) : undefined}
              />
            )
          )}

          {vista === 'fichas' && (
            fichaId ? (
              <FichaAplicada
                fichaId={fichaId}
                obraId={obraId}
                aoVoltar={() => ir('fichas')}
                aoAbrirNc={(id) => ir('defeitos', { nc: id })}
              />
            ) : (
              <ListaDeFichas
                obraId={obraId}
                podeAplicar={podeAplicar}
                aoAbrir={(id) => ir('fichas', { ficha: id })}
                aoIrParaModelos={() => ir('modelos')}
              />
            )
          )}

          {vista === 'modelos' && (
            <BibliotecaDeModelos
              modeloId={modeloId}
              aoAbrir={(id) => ir('modelos', { modelo: id })}
              aoVoltar={() => ir('modelos')}
            />
          )}
        </div>
      </div>

      {registrando && (
        <FormularioDeNc
          obraId={obraId}
          aoFechar={() => setRegistrando(false)}
          aoCriar={(nc) => { setRegistrando(false); ir('defeitos', { nc: nc.nc_id }) }}
        />
      )}
    </div>
  )
}
