import React from 'react';
import { useSearchParams } from 'react-router-dom';
import { useAuth } from '../../../hooks/useAuth';

/**
 * Mapeamento por Drone (funcoesODM) embutido no ERP.
 *
 * SSO sem segundo login: o shell injeta o token da IAM no Angular via query param
 * (`/drone/?token=...`). O AuthService do funcoesODM captura o token na primeira
 * carga, limpa a URL e suprime a tela de login (ver Fase 1). O acesso é
 * condicionado ao entitlement `drone` — o backend Java também recusa (403) quem
 * não tiver o módulo, como defesa em profundidade.
 *
 * Fase 3: se a página foi aberta a partir de uma Obra
 * (`/mapeamento-drone?empreendimento_id=..&obra_id=..`), repassa esse contexto ao
 * drone, que vincula novos projetos à obra/empreendimento corretos.
 */
const MapeamentoDronePage: React.FC = () => {
  const { hasModule } = useAuth();
  const [searchParams] = useSearchParams();
  const token = localStorage.getItem('token') ?? '';

  if (!hasModule('drone')) {
    return (
      <div>
        <h2>Mapeamento por Drone</h2>
        <p>Seu plano não inclui o módulo de drone. Fale com o administrador da sua conta.</p>
      </div>
    );
  }

  // Monta a URL do drone com o token e, se houver, o contexto de obra.
  const params = new URLSearchParams({ token });
  const empreendimentoId = searchParams.get('empreendimento_id');
  const obraId = searchParams.get('obra_id');
  if (empreendimentoId) params.set('empreendimento_id', empreendimentoId);
  if (obraId) params.set('obra_id', obraId);
  const src = `/drone/?${params.toString()}`;

  return (
    <iframe
      title="Mapeamento por Drone"
      src={src}
      style={{ width: '100%', height: 'calc(100vh - 40px)', border: 'none' }}
    />
  );
};

export default MapeamentoDronePage;
