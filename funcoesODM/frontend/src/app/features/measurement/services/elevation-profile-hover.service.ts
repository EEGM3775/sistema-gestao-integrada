/**
 * ElevationProfileHoverService
 *
 * Compartilha o estado de hover entre o ElevationProfileChartComponent
 * (quem escreve) e o MeasurementTabComponent (quem reage colocando/removendo
 * um marcador temporario no mapa Leaflet).
 *
 * Desacoplamento intencional: o chart nao conhece o mapa; o tab nao conhece
 * o chart. O servico e o canal de comunicacao entre os dois.
 */

import { Injectable, signal } from '@angular/core';

export interface ProfileHoverState {
  /** ID da medicao cujo perfil esta sendo exibido */
  measurementId: string;
  /** Coordenada geografica do ponto hovado no grafico */
  lat: number;
  lng: number;
  /** Elevacao (m) no ponto */
  elevation: number;
  /** Distancia acumulada (m) desde o inicio do perfil */
  distance: number;
}

@Injectable({ providedIn: 'root' })
export class ElevationProfileHoverService {

  /** Estado atual do hover — null quando o cursor nao esta sobre o grafico */
  readonly hoverState = signal<ProfileHoverState | null>(null);

  setHover(state: ProfileHoverState): void {
    this.hoverState.set(state);
  }

  clearHover(): void {
    this.hoverState.set(null);
  }
}
