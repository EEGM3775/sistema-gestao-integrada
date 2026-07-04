import React, { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import apiClient from '../../api/apiClient';
import { useAuth } from '../../hooks/useAuth';
import type { Empreendimento, Obra } from '../../hooks/useObraData';
import styles from './ObrasListPage.module.css';

const STATUS_LABEL: Record<string, string> = {
  planejamento: 'Planejamento',
  em_execucao: 'Em Execução',
  concluida: 'Concluída',
  cancelada: 'Cancelada',
};

const ObrasListPage: React.FC = () => {
  const { empreendimentoId } = useParams<{ empreendimentoId?: string }>();
  const navigate = useNavigate();
  const { token } = useAuth();

  const [empreendimentos, setEmpreendimentos] = useState<Empreendimento[]>([]);
  const [obras, setObras] = useState<Obra[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectedId = empreendimentoId ? parseInt(empreendimentoId, 10) : null;
  const authHeader = token ? { Authorization: `Bearer ${token}` } : {};

  useEffect(() => {
    apiClient.get('/empreendimentos/', { headers: authHeader })
      .then(r => setEmpreendimentos(r.data.results ?? r.data))
      .catch(() => setError('Erro ao carregar empreendimentos'));
  }, [token]);

  useEffect(() => {
    if (!selectedId) { setObras([]); return; }
    setLoading(true);
    apiClient.get(`/obras/?empreendimento=${selectedId}`, { headers: authHeader })
      .then(r => setObras(r.data.results ?? r.data))
      .catch(() => setError('Erro ao carregar obras'))
      .finally(() => setLoading(false));
  }, [selectedId, token]);

  const handleEmpreendimentoChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const id = e.target.value;
    navigate(id ? `/empreendimentos/${id}/obras` : '/obras');
  };

  const handleObraClick = (obra: Obra) => {
    const eId = obra.empreendimento ?? selectedId;
    if (eId) navigate(`/empreendimentos/${eId}/obras/${obra.obra_id}`);
  };

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h1>Obras</h1>
        <select
          className={styles.select}
          value={selectedId ?? ''}
          onChange={handleEmpreendimentoChange}
        >
          <option value="">Selecione um empreendimento…</option>
          {empreendimentos.map(e => (
            <option key={e.empreendimento_id} value={e.empreendimento_id}>
              {e.empreendimento}
            </option>
          ))}
        </select>
      </div>

      {error && <p className={styles.error}>{error}</p>}

      {!selectedId && (
        <p className={styles.placeholder}>Selecione um empreendimento para ver as obras.</p>
      )}

      {selectedId && loading && <p className={styles.placeholder}>Carregando obras…</p>}

      {selectedId && !loading && obras.length === 0 && (
        <p className={styles.placeholder}>Nenhuma obra encontrada para este empreendimento.</p>
      )}

      {obras.length > 0 && (
        <table className={styles.table}>
          <thead>
            <tr>
              <th>#</th>
              <th>Nome</th>
              <th>Endereço</th>
              <th>Status</th>
              <th>Início Previsto</th>
              <th>Fim Previsto</th>
            </tr>
          </thead>
          <tbody>
            {obras.map(obra => (
              <tr
                key={obra.obra_id}
                className={styles.row}
                onClick={() => handleObraClick(obra)}
              >
                <td>{obra.obra_id}</td>
                <td>{obra.nome_obra}</td>
                <td className={styles.endereco}>{obra.endereco}</td>
                <td>
                  <span className={`${styles.badge} ${styles[obra.status_obra]}`}>
                    {STATUS_LABEL[obra.status_obra] ?? obra.status_obra}
                  </span>
                </td>
                <td>{obra.data_inicio_prevista ?? '—'}</td>
                <td>{obra.data_fim_prevista ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
};

export default ObrasListPage;
