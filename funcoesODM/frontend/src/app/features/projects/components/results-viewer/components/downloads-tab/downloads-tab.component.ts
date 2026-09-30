import { Component, Input, Output, EventEmitter, signal, computed, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { SelectableAsset } from '../../models/results-viewer.model';

/**
 * Componente para gerenciar downloads de assets
 * Suporta seleção múltipla e download em lote
 */
@Component({
  selector: 'app-downloads-tab',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './downloads-tab.component.html',
  styleUrls: ['./downloads-tab.component.scss']
})
export class DownloadsTabComponent {
  @Input() set assets(value: SelectableAsset[]) {
    console.log('DownloadsTab received assets:', value);
    this.selectableAssets.set(value);
  }
  @Input() nodeodmTaskId?: string;

  @Output() downloadAsset = new EventEmitter<SelectableAsset>();
  @Output() downloadSelected = new EventEmitter<SelectableAsset[]>();
  @Output() downloadAllZip = new EventEmitter<void>();
  @Output() previewAsset = new EventEmitter<SelectableAsset>();
  @Output() assetsChange = new EventEmitter<SelectableAsset[]>();

  selectableAssets = signal<SelectableAsset[]>([]);

  selectedCount = computed(() => 
    this.selectableAssets().filter(a => a.selected).length
  );

  allSelected = computed(() => {
    const assets = this.selectableAssets();
    return assets.length > 0 && assets.every(a => a.selected);
  });

  someSelected = computed(() => 
    this.selectableAssets().some(a => a.selected)
  );

  toggleSelectAll(): void {
    const newState = !this.allSelected();
    const updated = this.selectableAssets().map(a => ({ ...a, selected: newState }));
    this.selectableAssets.set(updated);
    this.assetsChange.emit(updated);
  }

  onAssetSelectionChange(): void {
    // Força atualização do signal e emite para o pai
    const updated = [...this.selectableAssets()];
    this.selectableAssets.set(updated);
    this.assetsChange.emit(updated);
  }

  onDownloadAsset(asset: SelectableAsset): void {
    this.downloadAsset.emit(asset);
  }

  onDownloadSelected(): void {
    const selected = this.selectableAssets().filter(a => a.selected);
    this.downloadSelected.emit(selected);
  }

  onDownloadAllZip(): void {
    this.downloadAllZip.emit();
  }

  onPreviewAsset(asset: SelectableAsset): void {
    this.previewAsset.emit(asset);
  }

  canPreview(asset: SelectableAsset): boolean {
    return asset.name.includes('orthophoto') || 
           asset.name.includes('dsm') || 
           asset.name.includes('dtm') ||
           asset.name.includes('report') ||
           asset.name.includes('.pdf') ||
           asset.name.includes('.tif');
  }
}
