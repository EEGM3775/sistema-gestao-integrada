import React, { useEffect, useState } from 'react';
import apiClient from '../../../api/apiClient';
import { useAuth } from '../../../hooks/useAuth';
import styles from './Finances.module.css';

interface Transacao {
  transacao_id: number;
  descricao: string;
  valor: string;
  tipo: 'ENTRADA' | 'SAIDA';
  meio_pagamento: string;
  data_transacao: string;
}

interface Props {
  obraId: number;
}

const fmt = (v: string) =>
  parseFloat(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });

const Finances: React.FC<Props> = ({ obraId }) => {
  const { token, hasModule } = useAuth();
  const [transacoes, setTransacoes] = useState<Transacao[]>([]);
  const [loading, setLoading] = useState(true);

  const podeVer = hasModule('erp_financeiro');

  useEffect(() => {
    if (!podeVer) return;
    apiClient.get(`/erp/transacoes/?obra=${obraId}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then(r => setTransacoes(r.data.results ?? r.data))
      .finally(() => setLoading(false));
  }, [obraId, token, podeVer]);

  if (!podeVer) {
    return (
      <div className={styles.locked}>
        <span className={styles.lockIcon}>🔒</span>
        <p>Acesso ao módulo <strong>ERP Financeiro</strong> não disponível no seu plano.</p>
      </div>
    );
  }

  if (loading) return <p className={styles.empty}>Carregando transações…</p>;
  if (transacoes.length === 0) return <p className={styles.empty}>Nenhuma transação vinculada a esta obra.</p>;

  const totalEntradas = transacoes.filter(t => t.tipo === 'ENTRADA').reduce((s, t) => s + parseFloat(t.valor), 0);
  const totalSaidas = transacoes.filter(t => t.tipo === 'SAIDA').reduce((s, t) => s + parseFloat(t.valor), 0);

  return (
    <div>
      <div className={styles.summary}>
        <div className={styles.summaryCard}>
          <span className={styles.summaryLabel}>Entradas</span>
          <span className={`${styles.summaryValue} ${styles.entrada}`}>
            {totalEntradas.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })}
          </span>
        </div>
        <div className={styles.summaryCard}>
          <span className={styles.summaryLabel}>Saídas</span>
          <span className={`${styles.summaryValue} ${styles.saida}`}>
            {totalSaidas.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })}
          </span>
        </div>
        <div className={styles.summaryCard}>
          <span className={styles.summaryLabel}>Saldo</span>
          <span className={`${styles.summaryValue} ${(totalEntradas - totalSaidas) >= 0 ? styles.entrada : styles.saida}`}>
            {(totalEntradas - totalSaidas).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })}
          </span>
        </div>
      </div>

      <table className={styles.table}>
        <thead>
          <tr>
            <th>Descrição</th>
            <th>Tipo</th>
            <th>Valor</th>
            <th>Meio</th>
            <th>Data</th>
          </tr>
        </thead>
        <tbody>
          {transacoes.map(t => (
            <tr key={t.transacao_id}>
              <td>{t.descricao}</td>
              <td>
                <span className={`${styles.badge} ${styles[t.tipo.toLowerCase()]}`}>
                  {t.tipo === 'ENTRADA' ? 'Entrada' : 'Saída'}
                </span>
              </td>
              <td className={t.tipo === 'ENTRADA' ? styles.entrada : styles.saida}>
                {fmt(t.valor)}
              </td>
              <td>{t.meio_pagamento}</td>
              <td>{t.data_transacao ? t.data_transacao.slice(0, 10) : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default Finances;
