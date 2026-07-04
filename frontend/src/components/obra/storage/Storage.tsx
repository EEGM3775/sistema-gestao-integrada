import React from 'react';
import styles from './Storage.module.css';

interface Props {
  obraId: number;
}

const Storage: React.FC<Props> = ({ obraId: _ }) => (
  <div className={styles.placeholder}>
    <span className={styles.icon}>🏗</span>
    <p>
      O módulo <strong>SCM (Supply Chain Management)</strong> está em desenvolvimento.<br />
      O controle de estoque por obra estará disponível em breve.
    </p>
  </div>
);

export default Storage;
