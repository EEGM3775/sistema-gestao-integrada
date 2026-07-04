import React, { useState, useRef } from 'react';
import { Link } from 'react-router-dom';
import toast, { Toaster } from 'react-hot-toast';
import { useObraData } from '../../hooks/useObraData';
import type { TipoDocumento } from '../../hooks/useObraData';
import KpiDashboard from '../../components/obra/kpidashboard/KpiDashboard';
import DocumentsList from '../../components/obra/documentslist/DocumentsList';
import GanttChart from '../../components/obra/ganttchart/GanttChart';
import ObraTimeline from '../../components/obra/obratimeline/ObraTimeline';
import Finances from '../../components/obra/finances/Finances';
import Storage from '../../components/obra/storage/Storage';
import InteractiveMap from '../../components/obra/interactivemap/InteractiveMap';
import BluePrint from '../../components/obra/blueprint/BluePrint';
import styles from './ObraDetailPage.module.css';

type TabKey = 'visao' | 'cronograma' | 'diario' | 'financeiro' | 'estoque';

const TABS: { key: TabKey; label: string }[] = [
  { key: 'visao',       label: 'Visão Geral' },
  { key: 'cronograma',  label: 'Cronograma' },
  { key: 'diario',      label: 'Diário' },
  { key: 'financeiro',  label: 'Financeiro' },
  { key: 'estoque',     label: 'Estoque' },
];

const STATUS_LABEL: Record<string, string> = {
  planejamento: 'Planejamento', em_execucao: 'Em Execução',
  concluida: 'Concluída', cancelada: 'Cancelada',
};

const ObraDetailPage: React.FC = () => {
  const {
    loading, error, obraDetail, etapas, documentos,
    selectedEmpreendimentoId, selectedObraId,
    isUploadModalOpen, uploading,
    handleOpenUpload, handleCloseUpload, handleUpload,
  } = useObraData();

  const [activeTab, setActiveTab] = useState<TabKey>('visao');

  // Upload modal state
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadNome, setUploadNome] = useState('');
  const [uploadTipo, setUploadTipo] = useState<TipoDocumento>('outros');
  const [uploadDesc, setUploadDesc] = useState('');
  const fileRef = useRef<HTMLInputElement>(null);

  const handleSubmitUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!uploadFile || !uploadNome) return;
    try {
      await handleUpload(uploadFile, uploadNome, uploadTipo, uploadDesc);
      toast.success('Documento enviado com sucesso!');
      setUploadFile(null); setUploadNome(''); setUploadDesc('');
      if (fileRef.current) fileRef.current.value = '';
    } catch {
      toast.error('Erro ao enviar documento.');
    }
  };

  if (loading) return <div className={styles.state}>Carregando obra…</div>;
  if (error)   return <div className={`${styles.state} ${styles.error}`}>{error}</div>;
  if (!obraDetail) {
    return (
      <div className={styles.state}>
        Selecione uma obra na <Link to="/obras">lista de obras</Link>.
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <Toaster position="top-right" />

      {/* Breadcrumb */}
      <nav className={styles.breadcrumb}>
        <Link to="/obras">Obras</Link>
        <span>/</span>
        <span>{obraDetail.nome_obra}</span>
      </nav>

      {/* Header */}
      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>{obraDetail.nome_obra}</h1>
          <p className={styles.address}>{obraDetail.endereco}</p>
        </div>
        <span className={`${styles.statusBadge} ${styles[obraDetail.status_obra]}`}>
          {STATUS_LABEL[obraDetail.status_obra] ?? obraDetail.status_obra}
        </span>
      </div>

      {/* KPIs */}
      <KpiDashboard obra={obraDetail} etapas={etapas} />

      {/* Layout principal: sidebar esquerda + conteúdo com abas */}
      <div className={styles.layout}>
        {/* Coluna esquerda */}
        <aside className={styles.sidebar}>
          <section className={styles.sideSection}>
            <h3>Localização</h3>
            <InteractiveMap endereco={obraDetail.endereco} nomObra={obraDetail.nome_obra} />
          </section>

          <section className={styles.sideSection}>
            <h3>Documentos</h3>
            <DocumentsList documentos={documentos} onUpload={handleOpenUpload} />
          </section>

          <section className={styles.sideSection}>
            <h3>Projeto (3D)</h3>
            <BluePrint obraId={obraDetail.obra_id} />
          </section>
        </aside>

        {/* Coluna direita — abas */}
        <main className={styles.main}>
          <div className={styles.tabs}>
            {TABS.map(t => (
              <button
                key={t.key}
                className={`${styles.tab} ${activeTab === t.key ? styles.activeTab : ''}`}
                onClick={() => setActiveTab(t.key)}
              >
                {t.label}
              </button>
            ))}
          </div>

          <div className={styles.tabContent}>
            {activeTab === 'visao' && (
              <div className={styles.visaoGeral}>
                <dl className={styles.infoList}>
                  <dt>Início previsto</dt>
                  <dd>{obraDetail.data_inicio_prevista ?? '—'}</dd>
                  <dt>Fim previsto</dt>
                  <dd>{obraDetail.data_fim_prevista ?? '—'}</dd>
                  <dt>Início real</dt>
                  <dd>{obraDetail.data_inicio_real ?? '—'}</dd>
                  <dt>Fim real</dt>
                  <dd>{obraDetail.data_fim_real ?? '—'}</dd>
                  <dt>Orçamento previsto</dt>
                  <dd>
                    {obraDetail.orcamento_previsto
                      ? parseFloat(obraDetail.orcamento_previsto).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
                      : '—'}
                  </dd>
                </dl>
                {obraDetail.descricao && (
                  <p className={styles.descricao}>{obraDetail.descricao}</p>
                )}
              </div>
            )}
            {activeTab === 'cronograma' && (
              <GanttChart obraId={obraDetail.obra_id} etapas={etapas} />
            )}
            {activeTab === 'diario' && (
              <ObraTimeline obraId={obraDetail.obra_id} />
            )}
            {activeTab === 'financeiro' && (
              <Finances obraId={obraDetail.obra_id} />
            )}
            {activeTab === 'estoque' && (
              <Storage obraId={obraDetail.obra_id} />
            )}
          </div>
        </main>
      </div>

      {/* Modal de upload */}
      {isUploadModalOpen && (
        <div className={styles.modalOverlay} onClick={handleCloseUpload}>
          <div className={styles.modal} onClick={e => e.stopPropagation()}>
            <h2>Enviar Documento</h2>
            <form onSubmit={handleSubmitUpload} className={styles.form}>
              <label>
                Nome do documento *
                <input
                  required
                  value={uploadNome}
                  onChange={e => setUploadNome(e.target.value)}
                  placeholder="Ex: Projeto Arquitetônico Rev.01"
                />
              </label>
              <label>
                Tipo
                <select value={uploadTipo} onChange={e => setUploadTipo(e.target.value as TipoDocumento)}>
                  <option value="projeto">Projeto</option>
                  <option value="relatorio">Relatório</option>
                  <option value="memorial_descritivo">Memorial Descritivo</option>
                  <option value="alvara">Alvará</option>
                  <option value="contrato">Contrato</option>
                  <option value="licenca">Licença</option>
                  <option value="viabilidade">Viabilidade</option>
                  <option value="outros">Outros</option>
                </select>
              </label>
              <label>
                Descrição
                <textarea
                  value={uploadDesc}
                  onChange={e => setUploadDesc(e.target.value)}
                  rows={3}
                />
              </label>
              <label>
                Arquivo *
                <input
                  ref={fileRef}
                  type="file"
                  required
                  onChange={e => setUploadFile(e.target.files?.[0] ?? null)}
                />
              </label>
              <div className={styles.formActions}>
                <button type="button" className={styles.cancelBtn} onClick={handleCloseUpload}>
                  Cancelar
                </button>
                <button type="submit" className={styles.submitBtn} disabled={uploading}>
                  {uploading ? 'Enviando…' : 'Enviar'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default ObraDetailPage;
