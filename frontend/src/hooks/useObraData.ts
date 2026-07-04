import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import apiClient from '../api/apiClient';
import { useAuth } from './useAuth';

export interface Empreendimento {
  empreendimento_id: number;
  empreendimento: string;
  status_empreendimento: string;
}

export interface Obra {
  obra_id: number;
  nome_obra: string;
  endereco: string;
  status_obra: string;
  empreendimento: number | null;
  orcamento_previsto: string | null;
  data_inicio_prevista: string | null;
  data_fim_prevista: string | null;
  data_inicio_real: string | null;
  data_fim_real: string | null;
  descricao: string | null;
  data_cadastro: string;
}

export interface EtapaObra {
  etapa_id: number;
  obra: number;
  nome_etapa: string;
  ordem: number;
  percentual_conclusao: string;
  status_etapa: string;
  data_inicio_prevista: string | null;
  data_fim_prevista: string | null;
  data_inicio_real: string | null;
  data_fim_real: string | null;
  orcamento_previsto: string | null;
  responsavel: number | null;
}

export interface DocumentoObra {
  documento_id: number;
  obra: number;
  nome_documento: string;
  tipo_documento: string;
  versao: string | null;
  descricao: string | null;
  data_emissao: string | null;
  arquivo: string;
  status_documento: string;
  data_cadastro: string;
}

export type TipoDocumento =
  | 'projeto' | 'relatorio' | 'memorial_descritivo'
  | 'alvara' | 'contrato' | 'licenca' | 'viabilidade' | 'outros';

interface UseObraDataReturn {
  loading: boolean;
  error: string | null;
  empreendimentos: Empreendimento[];
  obras: Obra[];
  obraDetail: Obra | null;
  etapas: EtapaObra[];
  documentos: DocumentoObra[];
  selectedEmpreendimentoId: number | null;
  selectedObraId: number | null;
  isUploadModalOpen: boolean;
  uploading: boolean;
  handleEmpreendimentoChange: (id: number) => void;
  handleObraChange: (obraId: number, empreendimentoId: number) => void;
  handleOpenUpload: () => void;
  handleCloseUpload: () => void;
  handleUpload: (file: File, nome: string, tipo: TipoDocumento, descricao?: string) => Promise<void>;
  reloadDocumentos: () => void;
}

export function useObraData(): UseObraDataReturn {
  const { empreendimentoId, obraId } = useParams<{ empreendimentoId: string; obraId: string }>();
  const navigate = useNavigate();
  const { token } = useAuth();

  const parsedEmpreendimentoId = empreendimentoId ? parseInt(empreendimentoId, 10) : null;
  const parsedObraId = obraId ? parseInt(obraId, 10) : null;

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [empreendimentos, setEmpreendimentos] = useState<Empreendimento[]>([]);
  const [obras, setObras] = useState<Obra[]>([]);
  const [obraDetail, setObraDetail] = useState<Obra | null>(null);
  const [etapas, setEtapas] = useState<EtapaObra[]>([]);
  const [documentos, setDocumentos] = useState<DocumentoObra[]>([]);
  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false);
  const [uploading, setUploading] = useState(false);

  const authHeader = token ? { Authorization: `Bearer ${token}` } : {};

  // Carrega lista de empreendimentos ao montar
  useEffect(() => {
    apiClient.get('/empreendimentos/', { headers: authHeader })
      .then(r => setEmpreendimentos(r.data.results ?? r.data))
      .catch(() => setError('Erro ao carregar empreendimentos'));
  }, [token]);

  // Carrega obras quando empreendimento muda
  useEffect(() => {
    if (!parsedEmpreendimentoId) { setObras([]); return; }
    setLoading(true);
    apiClient.get(`/obras/?empreendimento=${parsedEmpreendimentoId}`, { headers: authHeader })
      .then(r => setObras(r.data.results ?? r.data))
      .catch(() => setError('Erro ao carregar obras'))
      .finally(() => setLoading(false));
  }, [parsedEmpreendimentoId, token]);

  // Carrega detalhes da obra selecionada
  useEffect(() => {
    if (!parsedObraId) { setObraDetail(null); setEtapas([]); setDocumentos([]); return; }
    setLoading(true);
    Promise.all([
      apiClient.get(`/obras/${parsedObraId}/`, { headers: authHeader }),
      apiClient.get(`/etapas-obras/?obra=${parsedObraId}`, { headers: authHeader }),
      apiClient.get(`/documentos-obras/?obra=${parsedObraId}`, { headers: authHeader }),
    ])
      .then(([obraRes, etapasRes, docsRes]) => {
        setObraDetail(obraRes.data);
        setEtapas(etapasRes.data.results ?? etapasRes.data);
        setDocumentos(docsRes.data.results ?? docsRes.data);
      })
      .catch(() => setError('Erro ao carregar detalhes da obra'))
      .finally(() => setLoading(false));
  }, [parsedObraId, token]);

  const handleEmpreendimentoChange = useCallback((id: number) => {
    navigate(`/empreendimentos/${id}/obras`);
  }, [navigate]);

  const handleObraChange = useCallback((oId: number, eId: number) => {
    navigate(`/empreendimentos/${eId}/obras/${oId}`);
  }, [navigate]);

  const handleOpenUpload = () => setIsUploadModalOpen(true);
  const handleCloseUpload = () => setIsUploadModalOpen(false);

  const handleUpload = async (file: File, nome: string, tipo: TipoDocumento, descricao = '') => {
    if (!parsedObraId) return;
    setUploading(true);
    try {
      const form = new FormData();
      form.append('obra', String(parsedObraId));
      form.append('nome_documento', nome);
      form.append('tipo_documento', tipo);
      form.append('descricao', descricao);
      form.append('arquivo', file);
      await apiClient.post('/documentos-obras/', form, {
        headers: { ...authHeader, 'Content-Type': 'multipart/form-data' },
      });
      // Recarrega documentos
      const r = await apiClient.get(`/documentos-obras/?obra=${parsedObraId}`, { headers: authHeader });
      setDocumentos(r.data.results ?? r.data);
      setIsUploadModalOpen(false);
    } catch {
      setError('Erro ao enviar documento');
    } finally {
      setUploading(false);
    }
  };

  const reloadDocumentos = useCallback(async () => {
    if (!parsedObraId) return;
    const r = await apiClient.get(`/documentos-obras/?obra=${parsedObraId}`, { headers: authHeader });
    setDocumentos(r.data.results ?? r.data);
  }, [parsedObraId, token]);

  return {
    loading,
    error,
    empreendimentos,
    obras,
    obraDetail,
    etapas,
    documentos,
    selectedEmpreendimentoId: parsedEmpreendimentoId,
    selectedObraId: parsedObraId,
    isUploadModalOpen,
    uploading,
    handleEmpreendimentoChange,
    handleObraChange,
    handleOpenUpload,
    handleCloseUpload,
    handleUpload,
    reloadDocumentos,
  };
}
