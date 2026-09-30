/**
 * Declaração de tipo para sql.js (SQLite compilado para WebAssembly).
 *
 * O pacote @types/sql.js não está disponível no registro npm padrão.
 * Esta declaração mínima resolve o erro TS7016 no build de produção.
 *
 * Tipos completos: https://github.com/sql-js/sql.js#readme
 */

declare module 'sql.js' {

  export interface SqlJsStatic {
    Database: typeof Database;
  }

  export interface QueryResults {
    columns: string[];
    values: (string | number | null | Uint8Array)[][];
  }

  export class Database {
    constructor(data?: ArrayLike<number> | Buffer | null);
    run(sql: string, params?: (string | number | null | Uint8Array)[]): Database;
    exec(sql: string): QueryResults[];
    export(): Uint8Array;
    close(): void;
  }

  export interface InitSqlJsConfig {
    locateFile?: (filename: string) => string;
  }

  function initSqlJs(config?: InitSqlJsConfig): Promise<SqlJsStatic>;
  export default initSqlJs;
}
