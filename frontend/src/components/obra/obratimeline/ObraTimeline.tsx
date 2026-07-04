import React, { useEffect, useState } from 'react';
import apiClient from '../../../api/apiClient';
import { useAuth } from '../../../hooks/useAuth';
import styles from './ObraTimeline.module.css';

interface DiarioObra {
  diario_obra_id: number;
  data: string;
  descricao: string;
  condicoes_climaticas: string;
  problemas_ocorrencias: string | null;
  usuario: number | null;
}

interface Props {
  obraId: number;
}

const ObraTimeline: React.FC<Props> = ({ obraId }) => {
  const { token } = useAuth();
  const [diarios, setDiarios] = useState<DiarioObra[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiClient.get(`/diario/diarios/?obra=${obraId}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then(r => setDiarios(r.data.results ?? r.data))
      .finally(() => setLoading(false));
  }, [obraId, token]);

  if (loading) return <p className={styles.empty}>Carregando diários…</p>;
  if (diarios.length === 0) return <p className={styles.empty}>Nenhum diário de obra registrado.</p>;

  return (
    <div className={styles.timeline}>
      {diarios.map(d => (
        <div key={d.diario_obra_id} className={styles.entry}>
          <div className={styles.dot} />
          <div className={styles.card}>
            <span className={styles.date}>
              {new Date(d.data).toLocaleDateString('pt-BR', { weekday: 'short', day: '2-digit', month: 'short', year: 'numeric' })}
            </span>
            <p className={styles.desc}>{d.descricao}</p>
            {d.condicoes_climaticas && (
              <span className={styles.tag}>🌤 {d.condicoes_climaticas}</span>
            )}
            {d.problemas_ocorrencias && (
              <p className={styles.problem}>⚠ {d.problemas_ocorrencias}</p>
            )}
          </div>
        </div>
      ))}
    </div>
  );
};

export default ObraTimeline;
