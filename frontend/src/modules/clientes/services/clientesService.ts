import apiClient from '../../../api/apiClient';
import type { Cliente } from '../../../types';

export type TipoDivergenciaAsaas = 'sem_documento' | 'nome_divergente' | 'vinculo_divergente';

export interface DivergenciaAsaas {
  cliente_id: number;
  nome: string;
  documento: string;
  tipo: TipoDivergenciaAsaas;
  detalhe: string;
  nome_gateway?: string;
  customer_id?: string;
  id_cliente_gateway?: string;
}

export interface RelatorioDivergenciasAsaas {
  total_clientes: number;
  total_divergencias: number;
  divergencias: DivergenciaAsaas[];
}

export const getClientes = () => {
  return apiClient.get<Cliente[]>('clientes/');
};

/** Divergências de identidade banco × Asaas (o que bloquearia/desviaria uma cobrança). */
export const getDivergenciasAsaas = () => {
  return apiClient.get<RelatorioDivergenciasAsaas>('clientes/divergencias-asaas/');
};

export const createCliente = (cliente: Omit<Cliente, 'cliente_id'>) => {
  return apiClient.post<Cliente>('clientes/', cliente);
};

export const updateCliente = (cliente_id: number, cliente: Partial<Cliente>) => {
  return apiClient.put<Cliente>(`clientes/${cliente_id}/`, cliente);
};

export const deleteCliente = (cliente_id: number) => {
  return apiClient.delete(`clientes/${cliente_id}/`);
};