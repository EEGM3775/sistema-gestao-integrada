import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useAuth } from '@/hooks/useAuth'
import { useFileUpload } from '@/hooks/useFileUpload'
import { useAnexarNaOcorrencia, useRegistrarOcorrencia } from '../hooks'
import { Escolhas } from '../components/Formulario'
import { SeletorDeLugar } from '../components/SeletorDeLugar'
import {
  Aviso, BotaoDaCamera, BotaoGrande, Cartao, Conjunto, EscolhaDeObra, Rotulado, Titulo,
  VoltarParaFrente,
} from './pecas'
import type { TipoOcorrencia } from '../types'
import { campoGrande } from '../estilos'
import { agoraLocal, primeiraFrase } from '../formato'
import { TIPOS_DE_OCORRENCIA } from '../vocabulario'

/** **Registrar o que aconteceu — sem atrito, e sem classificar.**
 *
 *  O que foi, quando e o que aconteceu; a foto da cena, se der. Classificar
 *  (afastamento, dias) não é do campo: quem é medido não classifica a própria
 *  medida. Quando alguém se feriu, a tela diz em voz alta que a CAT tem prazo
 *  — é a única coisa aqui que não pode esperar. */
export default function NovaOcorrenciaPage() {
  const [params] = useSearchParams()
  const { hasPermission } = useAuth()
  const { validate } = useFileUpload()
  const registrar = useRegistrarOcorrencia()
  const anexar = useAnexarNaOcorrencia()
  const numero = (chave: string) => Number(params.get(chave)) || null

  const [obra, setObra] = useState<number | null>(numero('obra'))
  const [local, setLocal] = useState<number | null>(numero('local'))
  const [atividade, setAtividade] = useState<number | null>(numero('atividade'))
  const [tipo, setTipo] = useState<TipoOcorrencia | null>(null)
  const [quando, setQuando] = useState(agoraLocal())
  const [descricao, setDescricao] = useState('')
  const [acidentado, setAcidentado] = useState('')
  const [foto, setFoto] = useState<File | null>(null)
  const [erro, setErro] = useState<string | null>(null)
  const [feito, setFeito] = useState<{ comVitima: boolean; semFoto: boolean } | null>(null)

  const comVitima = TIPOS_DE_OCORRENCIA.find((t) => t.valor === tipo)?.vitima ?? false

  if (!hasPermission('pdca.ocorrencia.registrar')) {
    return (
      <div style={{ padding: '14px 14px 4px', display: 'flex', flexDirection: 'column', gap: 16 }}>
        <VoltarParaFrente />
        <Aviso tom="accent">
          Registrar ocorrência exige permissão. Quem libera é o administrador da empresa —
          enquanto isso, avise o técnico de segurança agora, de viva voz.
        </Aviso>
      </div>
    )
  }

  return (
    <div style={{ padding: '14px 14px 4px', display: 'flex', flexDirection: 'column', gap: 16 }}>
      <VoltarParaFrente />
      <Titulo sub="Do quase-acidente ao acidente — todo registro vale.">Registrar uma ocorrência</Titulo>

      {feito && (
        <Aviso tom={feito.comVitima ? 'accent' : 'good'}>
          Registrada. O escritório já está vendo.
          {feito.comVitima && ' Alguém se feriu: a CAT tem prazo legal — avise o técnico de segurança e o RH agora.'}
          {feito.semFoto && ' A foto da cena não subiu; mande-a de novo pelo escritório.'}
        </Aviso>
      )}

      <Cartao>
        <Conjunto rotulo="O que foi">
          <Escolhas
            tamanho="lg"
            valor={tipo}
            aoEscolher={(t) => { setTipo(t); setFeito(null) }}
            opcoes={TIPOS_DE_OCORRENCIA.map((t) => ({ valor: t.valor, rotulo: t.rotulo, tom: t.tom }))}
          />
        </Conjunto>

        <Rotulado rotulo="O que aconteceu">
          <textarea
            rows={3} value={descricao} onChange={(e) => setDescricao(e.target.value)}
            style={{ ...campoGrande, resize: 'vertical' }}
          />
        </Rotulado>

        {comVitima && (
          <Rotulado rotulo="Quem se feriu">
            <input value={acidentado} onChange={(e) => setAcidentado(e.target.value)} style={campoGrande} />
          </Rotulado>
        )}

        <Rotulado rotulo="Quando">
          <input type="datetime-local" value={quando} max={agoraLocal()}
            onChange={(e) => setQuando(e.target.value)} style={campoGrande} />
        </Rotulado>

        <BotaoDaCamera foto={foto} aoMudar={setFoto} rotulo="Foto da cena (opcional)" />

        <EscolhaDeObra valor={obra} aoMudar={(o) => { setObra(o); setLocal(null); setAtividade(null) }} />
        {obra != null && (
          <SeletorDeLugar
            obraId={obra} local={local} atividade={atividade}
            aoMudarLocal={setLocal} aoMudarAtividade={setAtividade} grande
          />
        )}

        <Aviso tom="danger">{erro}</Aviso>

        <BotaoGrande
          tom={comVitima ? 'danger' : 'accent'}
          disabled={!obra || !tipo || !descricao.trim() || !quando || registrar.isPending}
          onClick={async () => {
            if (!obra || !tipo) return
            setErro(null)
            if (foto) {
              const problema = validate(foto)
              if (problema) { setErro(problema); return }
            }
            try {
              const nova = await registrar.mutateAsync({
                obra, tipo, ocorrido_em: quando, descricao: descricao.trim(),
                local, atividade, acidentado_nome: comVitima ? acidentado.trim() : '',
              })
              let semFoto = false
              if (foto) {
                try {
                  await anexar.mutateAsync({ ocorrencia: nova.ocorrencia_id, especie: 'cena', arquivo: foto })
                } catch {
                  semFoto = true
                }
              }
              setFeito({ comVitima, semFoto })
              setTipo(null)
              setDescricao('')
              setAcidentado('')
              setFoto(null)
              setQuando(agoraLocal())
            } catch (e) {
              setErro(primeiraFrase(e))
            }
          }}
        >
          {registrar.isPending ? 'Registrando…' : 'Registrar'}
        </BotaoGrande>
      </Cartao>
    </div>
  )
}
