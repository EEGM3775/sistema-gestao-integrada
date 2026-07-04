import './Table.css';

interface Column<T> {
  header: string;
  accessor: keyof T;
}

interface TableProps<T> {
  columns: Column<T>[];
  data: T[];
  onEdit?: (item: T) => void;
  onDelete?: (item: T) => void;
}

const Table = <T extends { cliente_id: any }>({ columns, data, onEdit, onDelete }: TableProps<T>) => {
  return (
    <div className="table-container">
      <table>
        <thead>
          <tr>
            {columns.map((col) => (
              <th key={String(col.accessor)}>{col.header}</th>
            ))}
            {(onEdit || onDelete) && <th>Ações</th>}
          </tr>
        </thead>
        <tbody>
          {data.map((item) => (
            <tr key={item.cliente_id}>
              {columns.map((col) => (
                <td key={`${item.cliente_id}-${String(col.accessor)}`}>{String(item[col.accessor] || '')}</td>
              ))}
              {(onEdit || onDelete) && (
                <td key={`${item.cliente_id}-actions`} className="actions">
                  {onEdit && <button className="action-btn edit" onClick={() => onEdit(item)}>Editar</button>}
                  {onDelete && <button className="action-btn delete" onClick={() => onDelete(item)}>Excluir</button>}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default Table;
