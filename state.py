from typing import Annotated, Optional, List, Dict, Any
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field


class EstadoAgente(TypedDict):
    # `add_messages` garante que novas mensagens sejam anexadas ao histórico, não sobrescritas
    messages: Annotated[list, add_messages]

    # Dados operacionais da execução atual (Gestão de Estado exigida no PDF)
    empresa_id: Optional[int]
    empresa_nome: Optional[str]
    assinatura_id: Optional[int]
    status_assinatura: Optional[str]
    saldo_atual: Optional[int]
    creditos_solicitados: Optional[int]

    # Controle de execução e limites operacionais
    iteracoes: int
    max_iteracoes: int
    limite_creditos: int


class AgentRequest(BaseModel):
    """Contrato de entrada da API FastAPI do Agente."""
    instrucao: str = Field(..., min_length=3, description="Solicitação em linguagem natural do analista de CS.")
    limite_creditos_override: Optional[int] = Field(
        default=3000, ge=1, le=10000, description="Ajuste dinâmico do teto operacional (padrão: 3.000 créditos)."
    )
    max_iteracoes_override: Optional[int] = Field(
        default=6, ge=2, le=15, description="Limite máximo de iterações no grafo para evitar loops."
    )
    saas_url_override: Optional[str] = Field(
        default=None, description="URL alternativa do SaaS Base (Docker oficial ou Mock SaaS)."
    )


class AgentResponse(BaseModel):
    """Resposta JSON estruturada para auditoria e integração via Swagger/Postman/Streamlit."""
    status: str = Field(..., description="SUCESSO, RECUSADO, AMBIGUIDADE ou CONSULTA")
    parecer_agente: str
    dados_operacionais: Dict[str, Any]
    iteracoes_executadas: int
