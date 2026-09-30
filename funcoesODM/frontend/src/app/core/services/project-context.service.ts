import { Injectable } from '@angular/core';

/**
 * Contexto de origem (ERP) do drone — Fase 3.
 *
 * Quando o shell (ERP) abre o drone a partir de uma Obra, injeta na URL
 * `?empreendimento_id=..&obra_id=..` (junto do token). Este serviço captura
 * esses IDs na carga e os fornece ao criar projetos, para vinculá-los à obra
 * correta no ERP (vínculo cross-DB, sem FK).
 *
 * Usa sessionStorage (escopo do iframe/aba): se a carga atual NÃO traz os
 * parâmetros (ex.: drone aberto solto pelo menu), o contexto é limpo — evita
 * vincular projetos a uma obra que não é mais a corrente.
 */
@Injectable({ providedIn: 'root' })
export class ProjectContextService {
  private readonly EMP_KEY = 'erp_empreendimento_id';
  private readonly OBRA_KEY = 'erp_obra_id';

  constructor() {
    this.captureFromUrl();
  }

  private captureFromUrl(): void {
    if (typeof window === 'undefined') return;
    const params = new URLSearchParams(window.location.search);
    const emp = params.get('empreendimento_id');
    const obra = params.get('obra_id');
    // A URL da carga atual é a autoridade do contexto.
    if (emp) sessionStorage.setItem(this.EMP_KEY, emp);
    else sessionStorage.removeItem(this.EMP_KEY);
    if (obra) sessionStorage.setItem(this.OBRA_KEY, obra);
    else sessionStorage.removeItem(this.OBRA_KEY);
  }

  get empreendimentoId(): number | null {
    const v = sessionStorage.getItem(this.EMP_KEY);
    return v ? Number(v) : null;
  }

  get obraId(): number | null {
    const v = sessionStorage.getItem(this.OBRA_KEY);
    return v ? Number(v) : null;
  }

  /** Há um contexto de obra/empreendimento ativo nesta sessão? */
  get hasContext(): boolean {
    return this.empreendimentoId !== null || this.obraId !== null;
  }

  clear(): void {
    sessionStorage.removeItem(this.EMP_KEY);
    sessionStorage.removeItem(this.OBRA_KEY);
  }
}
