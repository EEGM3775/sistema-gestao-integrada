import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useAuth } from '@/hooks/useAuth'
import { useFileUpload } from '@/hooks/useFileUpload'
import { useAbrirNc } from '../hooks'
import { campoGrande } from '../estilos'
import { Escolhas } from '../components/Formulario'
import { SeletorDeLugar } from '../components/SeletorDeLugar'
import {
  Aviso, BotaoDaCamera, BotaoGrande, Cartao, Conjunto, EscolhaDeObra, Rotulado, Titulo,
  VoltarParaFrente,
} from './pecas'
import type { GravidadeNc } from '../types'
import { primeiraFrase } from '../formato'
import { GRAVIDADES } from '../vocabulario'

/** **Abrir um defeito com foto — a tela abre pela câmera, não pelo formulário.**
 *
 *  A lição do Fieldwire e do Dalux aplicada ao que o backend já tinha: o
 *  defeito nasce como foto no lugar, e o texto vem depois. Obra, local e
 *  serviço chegam preenchidos quando se vem da frente (`?obra=&local=&atividade=`),
 *  para ninguém redigitar onde está. */
export default function NovoDefeitoPage() {
  const [params] = useSearchParams()
  const { hasPermission } = useAuth()
  const { validate } = useFileUpload()
  const abrir = useAbrirNc()
  const numero = (chave: string) => Number(params.get(chave)) || null

  const [obra, setObra] = useState<number | null>(numero('obra'))
  const [local, setLocal] = useState<number | null>(numero('local'))
  const [atividade, setAtividade] = useState<number | null>(numero('atividade'))
  const [foto, setFoto] = useState<File | null>(null)
  const [descricao, setDescricao] = useState('')
  const [gravidade, setGravidade] = useState<GravidadeNc | null>(null)
  const [erro, setErro] = useState<string | null>(null)
  const [feito, setFeito] = useState<string | null>(null)

  if (!hasPermission('pdca.nc.abrir')) {
    return (
      <div style={{ padding: '14px 14px 4px', display: 'flex', flexDirection: 'column', gap: 16 }}>
        <VoltarParaFrente />
        <Aviso tom="accent">
          Registrar defeito exige a permissão de abrir não-conformidade. Quem libera é o
          administrador da empresa — enquanto isso, avise o escritório.
        </Aviso>
      </div>
    )
  }

  return (
    <div style={{ padding: '14px 14px 4px', display: 'flex', flexDirection: 'column', gap: 16 }}>
      <VoltarParaFrente />
      <Titulo sub="Foto primeiro — o texto vem depois.">Registrar um defeito</Titulo>

      <Aviso tom="good">{feito}</Aviso>

      <Cartao>
        <BotaoDaCamera foto={foto} aoMudar={(f) => { setFoto(f); setFeito(null) }} rotulo="Fotografar o defeito" grande />

        <Rotulado rotulo="O que está errado">
          <textarea
            rows={3} value={descricao}
            onChange={(e) => { setDescricao(e.target.value); setFeito(null) }}
            style={{ ...campoGrande, resize: 'vertical' }}
          />
        </Rotulado>

        <Conjunto rotulo="Quanto pesa">
          <Escolhas
            tamanho="lg"
            valor={gravidade}
            aoEscolher={setGravidade}
            opcoes={GRAVIDADES.map((g) => ({ valor: g.valor, rotulo: `${g.rotulo} — ${g.explica}`, tom: g.tom }))}
          />
        </Conjunto>

        <EscolhaDeObra valor={obra} aoMudar={(o) => { setObra(o); setLocal(null); setAtividade(null) }} />

        {obra != null && (
          <SeletorDeLugar
            obraId={obra}
            local={local}
            atividade={atividade}
            aoMudarLocal={setLocal}
            aoMudarAtividade={setAtividade}
            grande
          />
        )}

        <Aviso tom="danger">{erro}</Aviso>

        <BotaoGrande
          disabled={!obra || !descricao.trim() || !gravidade || abrir.isPending}
          onClick={async () => {
            if (!obra || !gravidade) return
            setErro(null)
            if (foto) {
              const problema = validate(foto)
              if (problema) { setErro(problema); return }
            }
            try {
              await abrir.mutateAsync({
                corpo: { obra, descricao: descricao.trim(), gravidade, local, atividade },
                foto,
              })
              setFeito('Defeito registrado. O escritório já está vendo.')
              setFoto(null)
              setDescricao('')
              setGravidade(null)
            } catch (e) {
              setErro(primeiraFrase(e))
            }
          }}
        >
          {abrir.isPending ? 'Registrando…' : 'Registrar defeito'}
        </BotaoGrande>
      </Cartao>
    </div>
  )
}
