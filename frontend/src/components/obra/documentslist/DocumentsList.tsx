import React, { useState } from 'react';
import type { DocumentoObra } from '../../../hooks/useObraData';
import styles from './DocumentsList.module.css';

const TIPO_LABEL: Record<string, string> = {
  projeto: 'Projeto', relatorio: 'Relatório', memorial_descritivo: 'Memorial Descritivo',
  alvara: 'Alvará', contrato: 'Contrato', licenca: 'Licença',
  viabilidade: 'Viabilidade', outros: 'Outros',
};

const STATUS_LABEL: Record<string, string> = {
  rascunho: 'Rascunho', em_revisao: 'Em Revisão', aprovacao: 'Aprovação',
  correcoes: 'Correções', aprovado: 'Aprovado', rejeitado: 'Rejeitado',
  publicado: 'Publicado', cancelado: 'Cancelado',
};

interface Props {
  documentos: DocumentoObra[];
  onUpload?: () => void;
}

const DocumentsList: React.FC<Props> = ({ documentos, onUpload }) => {
  const [filter, setFilter] = useState('');

  const filtered = documentos.filter(d =>
    d.nome_documento.toLowerCase().includes(filter.toLowerCase()) ||
    (TIPO_LABEL[d.tipo_documento] ?? d.tipo_documento).toLowerCase().includes(filter.toLowerCase())
  );

  return (
    <div className={styles.container}>
      <div className={styles.toolbar}>
        <input
          className={styles.search}
          placeholder="Buscar documento…"
          value={filter}
          onChange={e => setFilter(e.target.value)}
        />
        {onUpload && (
          <button className={styles.uploadBtn} onClick={onUpload}>
            + Enviar documento
          </button>
        )}
      </div>

      {filtered.length === 0 ? (
        <p className={styles.empty}>Nenhum documento encontrado.</p>
      ) : (
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Nome</th>
              <th>Tipo</th>
              <th>Versão</th>
              <th>Status</th>
              <th>Data</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {filtered.map(doc => (
              <tr key={doc.documento_id}>
                <td>{doc.nome_documento}</td>
                <td>{TIPO_LABEL[doc.tipo_documento] ?? doc.tipo_documento}</td>
                <td>{doc.versao ?? '—'}</td>
                <td>
                  <span className={`${styles.badge} ${styles[doc.status_documento]}`}>
                    {STATUS_LABEL[doc.status_documento] ?? doc.status_documento}
                  </span>
                </td>
                <td>{doc.data_cadastro ? doc.data_cadastro.slice(0, 10) : '—'}</td>
                <td>
                  {doc.arquivo && (
                    <a
                      href={doc.arquivo}
                      target="_blank"
                      rel="noopener noreferrer"
                      className={styles.downloadLink}
                    >
                      Download
                    </a>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
};

export default DocumentsList;
