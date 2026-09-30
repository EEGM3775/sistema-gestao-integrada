/**
 * GeoTiffCacheService
 *
 * Cache singleton de GeoTIFFs para a sessao do browser.
 *
 * Problema que resolve:
 *   parseGeoraster() usa um Web Worker e TRANSFERE o ArrayBuffer via postMessage.
 *   Apos a transferencia o buffer original fica "detached" (byteLength = 0) e
 *   qualquer reuso seguinte lanca DataCloneError.
 *
 * Solucao:
 *   Internamente armazenamos os bytes como Uint8Array (que nao e transferivel).
 *   A cada get() entregamos um ArrayBuffer NOVO criado via slice() — o chamador
 *   pode transferi-lo livremente sem afetar o cache.
 */

import { Injectable } from '@angular/core';

export interface DownloadProgress {
  percent: number;
  receivedBytes: number;
  totalBytes: number;
}

@Injectable({ providedIn: 'root' })
export class GeoTiffCacheService {

  // Bytes brutos — Uint8Array nao e transferivel, nunca fica detached
  private store   = new Map<string, Uint8Array>();
  private pending = new Map<string, Promise<Uint8Array>>();

  // Georaster parseado por URL — sobrevive a destroy/recreate de componentes
  private georasters = new Map<string, any>();

  /** true se os bytes ja estao em cache (retorno sera instantaneo). */
  has(url: string): boolean {
    return this.store.has(url);
  }

  /** Guarda o georaster parseado associado a uma URL. */
  setGeoRaster(url: string, georaster: any): void {
    this.georasters.set(url, georaster);
  }

  /** Retorna o georaster cacheado, ou null se ainda nao foi parseado. */
  getGeoRaster(url: string): any | null {
    return this.georasters.get(url) ?? null;
  }

  hasGeoRaster(url: string): boolean {
    return this.georasters.has(url);
  }

  /**
   * Retorna um ArrayBuffer novo com os bytes do arquivo.
   * Cada chamada entrega uma copia independente — pode ser transferida para
   * um Worker sem invalidar o cache.
   */
  async get(
    url: string,
    onProgress?: (p: DownloadProgress) => void
  ): Promise<ArrayBuffer> {
    const bytes = await this.getBytes(url, onProgress);
    // slice() cria um novo ArrayBuffer — o cache (Uint8Array) permanece intacto
    return bytes.slice().buffer;
  }

  evict(url?: string): void {
    if (url) { this.store.delete(url); this.pending.delete(url); this.georasters.delete(url); }
    else      { this.store.clear();    this.pending.clear();     this.georasters.clear(); }
  }

  // ─── Interno ───────────────────────────────────────────────────────────────

  private async getBytes(
    url: string,
    onProgress?: (p: DownloadProgress) => void
  ): Promise<Uint8Array> {
    if (this.store.has(url)) {
      const bytes = this.store.get(url)!;
      onProgress?.({ percent: 100, receivedBytes: bytes.byteLength, totalBytes: bytes.byteLength });
      return bytes;
    }

    if (this.pending.has(url)) {
      return this.pending.get(url)!;
    }

    const promise = this.download(url, onProgress)
      .then(bytes => { this.store.set(url, bytes); this.pending.delete(url); return bytes; })
      .catch(err  => { this.pending.delete(url); throw err; });

    this.pending.set(url, promise);
    return promise;
  }

  private async download(
    url: string,
    onProgress?: (p: DownloadProgress) => void
  ): Promise<Uint8Array> {
    const response = await fetch(url);
    if (!response.ok) throw new Error(`HTTP ${response.status} — ${response.statusText}`);

    const total = parseInt(response.headers.get('content-length') ?? '0', 10);

    if (!response.body || total === 0) {
      const buf = await response.arrayBuffer();
      const bytes = new Uint8Array(buf);
      onProgress?.({ percent: 100, receivedBytes: bytes.byteLength, totalBytes: bytes.byteLength });
      return bytes;
    }

    const reader = response.body.getReader();
    const chunks: Uint8Array[] = [];
    let received = 0;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      chunks.push(value);
      received += value.byteLength;
      onProgress?.({
        percent: Math.min(99, Math.round((received / total) * 100)),
        receivedBytes: received,
        totalBytes: total
      });
    }

    const result = new Uint8Array(received);
    let offset = 0;
    for (const chunk of chunks) { result.set(chunk, offset); offset += chunk.byteLength; }
    onProgress?.({ percent: 100, receivedBytes: received, totalBytes: received });
    return result;
  }
}
