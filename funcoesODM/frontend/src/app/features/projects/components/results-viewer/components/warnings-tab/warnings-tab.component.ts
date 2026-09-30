import { Component, Input, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { TaskWarnings, WarningSummary } from '../../../../services/results.service';

/**
 * Componente para exibir avisos de processamento
 * Mostra categorias de avisos e log completo
 */
@Component({
    selector: 'app-warnings-tab',
    imports: [CommonModule],
    templateUrl: './warnings-tab.component.html',
    styleUrls: ['./warnings-tab.component.scss']
})
export class WarningsTabComponent {
  @Input() set warnings(value: TaskWarnings | null) {
    this.taskWarnings.set(value);
  }
  @Input() set loading(value: boolean) {
    this.loadingWarnings.set(value);
  }

  taskWarnings = signal<TaskWarnings | null>(null);
  loadingWarnings = signal(false);
  showRawWarnings = signal(false);

  warningCount = computed(() => {
    const warnings = this.taskWarnings();
    return warnings?.unique_warning_count ?? 0;
  });

  warningSummary = computed(() => {
    const warnings = this.taskWarnings();
    return warnings?.summary ?? [];
  });

  rawWarningsText = computed(() => {
    const warnings = this.taskWarnings();
    return warnings?.warnings.join('\n') ?? '';
  });

  toggleRawWarnings(): void {
    this.showRawWarnings.update(v => !v);
  }
}
