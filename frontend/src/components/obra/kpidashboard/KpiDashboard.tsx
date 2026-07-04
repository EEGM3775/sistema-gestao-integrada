import React, { useEffect, useState } from 'react';
import type { Obra, EtapaObra } from '../../../hooks/useObraData';
import styles from './KpiDashboard.module.css';
import apiClient from '../../../api/apiClient';

interface Props {
  obra: Obra;
  etapas: EtapaObra[];
}

const fmt = (v: string | null) =>
  v ? parseFloat(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' }) : '—';

const KpiDashboard: React.FC<Props> = ({ obra, etapas }) => {
  const totalEtapas = etapas.length;
  const concluidas = etapas.filter(e => e.status_etapa === 'concluida').length;

  const [progressoGeral, setProgressoGeral] = useState<number>(() => {
    if (totalEtapas === 0) return 0;
    return Math.round(etapas.reduce((acc, e) => acc + parseFloat(e.percentual_conclusao || '0'), 0) / totalEtapas);
  });

  useEffect(() => {
    let mounted = true;
    if (!obra || !obra.obra_id) {
      // recomputa localmente
      const fallback = totalEtapas === 0 ? 0 : Math.round(etapas.reduce((acc, e) => acc + parseFloat(e.percentual_conclusao || '0'), 0) / totalEtapas);
      setProgressoGeral(fallback);
      return;
    }

    apiClient.get(`/obras/${obra.obra_id}/progresso/`)
      .then(r => {
        if (!mounted) return;
        const p = r?.data?.progresso;
        if (typeof p === 'number') setProgressoGeral(p);
      })
      .catch(() => {
        if (!mounted) return;
        const fallback = totalEtapas === 0 ? 0 : Math.round(etapas.reduce((acc, e) => acc + parseFloat(e.percentual_conclusao || '0'), 0) / totalEtapas);
        setProgressoGeral(fallback);
      });

    return () => { mounted = false; };
  }, [obra, etapas]);

  const orcamento = obra.orcamento_previsto ? parseFloat(obra.orcamento_previsto) : null;

  return (
    <div className={styles.grid}>
      <div className={styles.card}>
        <span className={styles.label}>Progresso Geral</span>
        <div className={styles.progressBar}>
          <div className={styles.progressFill} style={{ width: `${progressoGeral}%` }} />
        </div>
        <span className={styles.value}>{progressoGeral}%</span>
      </div>

      <div className={styles.card}>
        <span className={styles.label}>Etapas</span>
        <span className={styles.bigValue}>{concluidas}<span className={styles.total}>/{totalEtapas}</span></span>
        <span className={styles.sub}>concluídas</span>
      </div>

      <div className={styles.card}>
        <span className={styles.label}>Orçamento Previsto</span>
        <span className={styles.bigValue}>{fmt(obra.orcamento_previsto)}</span>
      </div>

      <div className={styles.card}>
        <span className={styles.label}>Status</span>
        <span className={`${styles.statusBadge} ${styles[obra.status_obra]}`}>
          {obra.status_obra.replace('_', ' ')}
        </span>
      </div>
    </div>
  );
};

export default KpiDashboard;
