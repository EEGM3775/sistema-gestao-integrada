import React, { useEffect, useRef, useState } from 'react';
import Gantt from 'frappe-gantt';
import type { Task } from 'frappe-gantt';
import apiClient from '../../../api/apiClient';
import { useAuth } from '../../../hooks/useAuth';
import type { EtapaObra } from '../../../hooks/useObraData';
import styles from './GanttChart.module.css';

interface Props {
  obraId: number;
  etapas?: EtapaObra[];
}

function etapaToTask(e: EtapaObra): Task | null {
  const start = e.data_inicio_real ?? e.data_inicio_prevista;
  const end = e.data_fim_real ?? e.data_fim_prevista;
  if (!start || !end) return null;
  return {
    id: String(e.etapa_id),
    name: e.nome_etapa,
    start,
    end,
    progress: parseFloat(e.percentual_conclusao),
  };
}

const VIEW_MODES = ['Day', 'Week', 'Month'] as const;

const GanttChart: React.FC<Props> = ({ obraId, etapas: etapasProp }) => {
  const { token } = useAuth();
  const containerRef = useRef<HTMLDivElement>(null);
  const ganttRef = useRef<Gantt | null>(null);
  const [etapas, setEtapas] = useState<EtapaObra[]>(etapasProp ?? []);
  const [viewMode, setViewMode] = useState<string>('Week');
  const [loading, setLoading] = useState(!etapasProp);

  useEffect(() => {
    if (etapasProp) { setEtapas(etapasProp); return; }
    setLoading(true);
    apiClient.get(`/etapas-obras/?obra=${obraId}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then(r => setEtapas(r.data.results ?? r.data))
      .finally(() => setLoading(false));
  }, [obraId, token, etapasProp]);

  useEffect(() => {
    if (!containerRef.current || etapas.length === 0) return;
    const tasks: Task[] = etapas.map(etapaToTask).filter(Boolean) as Task[];
    if (tasks.length === 0) return;

    containerRef.current.innerHTML = '';
    ganttRef.current = new Gantt(containerRef.current, tasks, {
      view_mode: viewMode as 'Day' | 'Week' | 'Month',
      language: 'pt',
    });
  }, [etapas, viewMode]);

  if (loading) return <p className={styles.empty}>Carregando cronograma…</p>;

  const tasksWithDates = etapas.filter(e =>
    (e.data_inicio_real ?? e.data_inicio_prevista) && (e.data_fim_real ?? e.data_fim_prevista)
  );

  if (tasksWithDates.length === 0) {
    return <p className={styles.empty}>Nenhuma etapa com datas cadastradas para exibir o cronograma.</p>;
  }

  return (
    <div className={styles.wrapper}>
      <div className={styles.toolbar}>
        {VIEW_MODES.map(m => (
          <button
            key={m}
            className={`${styles.modeBtn} ${viewMode === m ? styles.active : ''}`}
            onClick={() => setViewMode(m)}
          >
            {m === 'Day' ? 'Dia' : m === 'Week' ? 'Semana' : 'Mês'}
          </button>
        ))}
      </div>
      <div ref={containerRef} className={styles.gantt} />
    </div>
  );
};

export default GanttChart;
