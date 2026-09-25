import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { HardHat, MessagesSquare, Siren } from 'lucide-react'
import { Btn, Card, Empty, Loading } from '@/components/malha'
import { useAuth } from '@/hooks/useAuth'
import { usePdca } from '../contexto'
import { usePostoDaSeguranca } from '../hooks'
import { DocumentoDoDds, ListaDeDds } from '../components/DialogoDeSeguranca'
import { DocumentoDaOcorrencia } from '../components/DocumentoDaOcorrencia'
import { FilaDeDecisao } from '../components/FilaDeDecisao'
import { FormularioDeOcorrencia } from '../components/FormularioDeOcorrencia'
import { ListaDeOcorrencias } from '../components/ListaDeOcorrencias'
import { PainelDeSeguranca } from '../components/PainelDeSeguranca'
import { SemPermissaoAviso } from '../components/SemPermissaoAviso'
import { VistasDoPosto, type VistaDoPosto } from '../components/VistasDoPosto'

type Vista = 'hoje' | 'ocorrencias' | 'dds'

const VISTAS: VistaDoPosto<Vista>[] = [
  { chave: 'hoje', rotulo: 'O que pede ação', icone: Siren },
  { chave: 'ocorrencias', rotulo: 'Ocorrências', icone: HardHat },
  { chave: 'dds', rotulo: 'Diálogos de segurança', icone: MessagesSquare },
]

function vistaDoEndereco(params: URLSearchParams): Vista {
  const pedida = params.get('v')
  if (pedida && VISTAS.some((v) => v.chave === pedida)) return pedida as Vista
  if (params.get('ocorrencia')) return 'ocorrencias'
  if (params.get('dds')) return 'dds'
  return 'hoje'
}

/** **SEGURANÇA** — o que fazemos para ninguém se machucar, e o que fazemos
 *  quando alguém se machuca?
 *
 *  Posto separado da qualidade de propósito: a ocorrência tem prazo legal e
 *  dado de saúde, e não pode esperar numa fila atrás de um defeito de pintura.
 *  Abre pela fila — a CAT no topo, com o prazo correndo — ao lado dos números
 *  que o sistema sabe e dos dois que ele diz não saber. */
export default function SegurancaPage() {
  const { obraId } = usePdca()
  const { hasPermission } = useAuth()
  const [params, setParams] = useSearchParams()
  const [registrando, setRegistrando] = useState(false)
  const posto = usePostoDaSeguranca(obraId)

  const vista = vistaDoEndereco(params)
  const ocorrenciaId = Number(params.get('ocorrencia')) || null
  const ddsId = Number(params.get('dds')) || null
  const podeVer = hasPermission('pdca.ocorrencia.view')
  const podeRegistrar = hasPermission('pdca.ocorrencia.registrar')
  const podeVerDds = hasPermission('pdca.dds.view')

  function ir(qual: Vista, doc?: { ocorrencia?: number; dds?: number }) {
    const novo = new URLSearchParams()
    novo.set('v', qual)
    if (doc?.ocorrencia) novo.set('ocorrencia', String(doc.ocorrencia))
    if (doc?.dds) novo.set('dds', String(doc.dds))
    setParams(novo)
  }

  if (posto.isLoading) return <Loading o="a segurança da obra" />
  if (posto.isError || !posto.data) {
    return (
      <div style={{ padding: 26 }}>
        <Card>
          <Empty>
            Não foi possível carregar a segurança desta obra. Verifique a conexão e
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
        titulo="Segurança"
        sub="diária no diálogo · imediata na ocorrência"
        vistas={VISTAS}
        atual={vista}
        aoEscolher={(v) => ir(v)}
        contagem={{ hoje: dados.fila.total || undefined }}
      />

      <div style={{ flex: 1, minHeight: 0, overflow: 'auto' }}>
        <div style={{ padding: '18px 20px 34px', maxWidth: 1240 }}>
          {vista === 'hoje' && (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(420px, 1fr))', gap: 24, alignItems: 'start' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                <FilaDeDecisao
                  fila={dados.fila}
                  obraId={obraId}
                  titulo="O que pede ação"
                  noPosto
                  vazio={
                    <>
                      <strong style={{ color: 'var(--ink-2)' }}>Nada esperando decisão.</strong>
                      <br />
                      Nenhuma CAT por comunicar, nenhuma ocorrência sem classificação e
                      nenhuma sem investigação aberta.
                    </>
                  }
                />
                {podeRegistrar && (
                  <Btn variant="primary" onClick={() => setRegistrando(true)} style={{ alignSelf: 'flex-start' }}>
                    Registrar ocorrência
                  </Btn>
                )}
              </div>
              {dados.indicadores ? (
                <PainelDeSeguranca
                  indicadores={dados.indicadores}
                  interditadas={dados.frentes_interditadas}
                  obraId={obraId}
                />
              ) : (
                <SemPermissaoAviso itens={dados.sem_permissao} />
              )}
            </div>
          )}

          {vista === 'ocorrencias' && (
            !podeVer ? (
              <SemPermissaoAviso itens={dados.sem_permissao} />
            ) : ocorrenciaId ? (
              <DocumentoDaOcorrencia
                ocorrenciaId={ocorrenciaId}
                obraId={obraId}
                aoVoltar={() => ir('ocorrencias')}
              />
            ) : (
              <ListaDeOcorrencias
                obraId={obraId}
                aoAbrir={(id) => ir('ocorrencias', { ocorrencia: id })}
                aoRegistrar={podeRegistrar ? () => setRegistrando(true) : undefined}
              />
            )
          )}

          {vista === 'dds' && (
            !podeVerDds ? (
              <SemPermissaoAviso
                itens={[{
                  bloco: 'dds', o_que: 'os diálogos de segurança desta obra',
                  permissao: 'pdca.dds.view',
                  motivo: 'Você não tem permissão para ver os diálogos de segurança.',
                }]}
              />
            ) : ddsId ? (
              <DocumentoDoDds ddsId={ddsId} aoVoltar={() => ir('dds')} />
            ) : (
              <ListaDeDds obraId={obraId} aoAbrir={(id) => ir('dds', { dds: id })} />
            )
          )}
        </div>
      </div>

      {registrando && (
        <FormularioDeOcorrencia
          obraId={obraId}
          aoFechar={() => setRegistrando(false)}
          aoCriar={(o) => { setRegistrando(false); ir('ocorrencias', { ocorrencia: o.ocorrencia_id }) }}
        />
      )}
    </div>
  )
}
