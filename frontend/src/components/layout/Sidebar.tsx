import React from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../../hooks/useAuth';
import './Sidebar.css';

const Sidebar: React.FC = () => {
  const { hasModule } = useAuth();

  return (
    <div className="sidebar">
      <div className="sidebar-header">
        <h3>SGI</h3>
      </div>
      <nav className="sidebar-nav">
        <ul>
          <li><Link to="/">Dashboard</Link></li>
          <li><Link to="/clientes">Clientes</Link></li>
          <li><Link to="/empreendimentos">Empreendimentos</Link></li>
          <li><Link to="/obras">Obras</Link></li>
          <li><Link to="/diarios-obra">Diário de Obra</Link></li>
          <li><Link to="/erp">Financeiro (ERP)</Link></li>
          <li><Link to="/fornecedores">Fornecedores</Link></li>
          {/* Item condicional ao entitlement do módulo (aparece/some conforme o plano) */}
          {hasModule('drone') && (
            <li><Link to="/mapeamento-drone">Mapeamento por Drone</Link></li>
          )}
        </ul>
      </nav>
    </div>
  );
};

export default Sidebar;
