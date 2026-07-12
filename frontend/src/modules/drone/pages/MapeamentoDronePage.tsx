import React, { useEffect, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useAuth } from '../../../hooks/useAuth';
import { getAccessToken, onAccessTokenChange } from '../../../api/tokenStore';

/**
 * Mapeamento por Drone (funcoesODM) embutido no ERP.
 *
 * SSO sem segundo login (Fase 10.6): o shell **não** injeta mais o token na URL
 * (`?token=`). Em vez disso, entrega o access token da IAM ao Angular via
 * `postMessage` (mesma origem) e o **reenvia a cada rotação** (~15 min), de modo
 * que a sessão do drone nunca vence no meio. O access token fica em memória nos
 * dois lados; o refresh vive só no cookie HttpOnly. Acesso condicionado ao
 * entitlement `drone` (o backend Java também recusa 403 — defesa em profundidade).
 *
 * Fase 3: contexto de Obra (`?empreendimento_id=..&obra_id=..`) segue na query
 * (não é segredo) e é repassado ao drone para vincular novos projetos.
 */
const MapeamentoDronePage: React.FC = () => {
  const { hasModule } = useAuth();
  const [searchParams] = useSearchParams();
  const iframeRef = useRef<HTMLIFrameElement>(null);

  const empreendimentoId = searchParams.get('empreendimento_id');
  const obraId = searchParams.get('obra_id');

  useEffect(() => {
    const alvo = window.location.origin;
    const enviarToken = () => {
      const token = getAccessToken();
      const win = iframeRef.current?.contentWindow;
      if (win && token) win.postMessage({ type: 'sgi-access-token', token }, alvo);
    };
    // O drone (filho) pede o token ao iniciar; e reenviamos a cada rotação.
    const onMsg = (e: MessageEvent) => {
      if (e.origin === alvo && e.data?.type === 'sgi-request-token') enviarToken();
    };
    window.addEventListener('message', onMsg);
    const desinscrever = onAccessTokenChange(() => enviarToken());
    return () => {
      window.removeEventListener('message', onMsg);
      desinscrever();
    };
  }, []);

  if (!hasModule('drone')) {
    return (
      <div>
        <h2>Mapeamento por Drone</h2>
        <p>Seu plano não inclui o módulo de drone. Fale com o administrador da sua conta.</p>
      </div>
    );
  }

  // Só o contexto de obra vai na URL (sem token).
  const params = new URLSearchParams();
  if (empreendimentoId) params.set('empreendimento_id', empreendimentoId);
  if (obraId) params.set('obra_id', obraId);
  const qs = params.toString();
  const src = `/drone/${qs ? `?${qs}` : ''}`;

  return (
    <iframe
      ref={iframeRef}
      title="Mapeamento por Drone"
      src={src}
      onLoad={() => {
        const token = getAccessToken();
        const win = iframeRef.current?.contentWindow;
        if (win && token) win.postMessage({ type: 'sgi-access-token', token }, window.location.origin);
      }}
      style={{ width: '100%', height: 'calc(100vh - 40px)', border: 'none' }}
    />
  );
};

export default MapeamentoDronePage;
