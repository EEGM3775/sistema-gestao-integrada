import React from 'react';
import styles from './BluePrint.module.css';
import { useAuth } from '../../../hooks/useAuth';

interface Props {
  obraId: number;
}

const BluePrint: React.FC<Props> = ({ obraId: _ }) => {
  const { hasModule } = useAuth();

  if (!hasModule('aps')) {
    return (
      <div className={styles.locked}>
        <span className={styles.icon}>🔒</span>
        <p>
          O módulo <strong>APS (Autodesk Platform Services)</strong> não está disponível
          no seu plano. Contrate o módulo para acessar o visualizador 3D de plantas e projetos.
        </p>
      </div>
    );
  }

  return (
    <div className={styles.stub}>
      <span className={styles.icon}>🏛</span>
      <p>Visualizador 3D em integração. Disponível em breve.</p>
    </div>
  );
};

export default BluePrint;
