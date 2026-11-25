import os
import httpx
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from langchain_core.tools import tool

# Configuração dinâmica ajustável pela FastAPI / Dashboard Streamlit em tempo real
RUNTIME_CONFIG = {
    "saas_base_url": os.getenv("SAAS_API_BASE_URL", "http://localhost:8000"),
    "max_credits": int(os.getenv("MAX_CREDITS_PER_OPERATION", "3000")),
    "timeout": float(os.getenv("SAAS_API_TIMEOUT", "10.0")),
}


# ==============================================================================
# 1. FERRAMENTAS COM ENTRADA E SAÍDA ESTRUTURADAS (Pydantic - Padrão agente2.py)
# ==============================================================================

class BuscarEmpresaInput(BaseModel):
    nome: str = Field(..., min_length=2, description="Nome fantasia ou termo parcial da empresa cliente.")


class BuscarEmpresaOutput(BaseModel):
    termo_buscado: str
    encontrada: bool
    ambigua: bool
    total_encontradas: int
    empresas: List[Dict[str, Any]]
    mensagem: str


@tool(args_schema=BuscarEmpresaInput)
def buscar_empresa(nome: str) -> dict:
    """Busca empresas cadastradas no SaaS (GET /empresas?nome=...) a partir do nome fantasia."""
    url = f"{RUNTIME_CONFIG['saas_base_url']}/empresas"
    try:
        with httpx.Client(timeout=RUNTIME_CONFIG["timeout"]) as client:
            resp = client.get(url, params={"nome": nome.strip()})
            resp.raise_for_status()
            empresas = resp.json()

        if not empresas:
            saida = BuscarEmpresaOutput(
                termo_buscado=nome,
                encontrada=False,
                ambigua=False,
                total_encontradas=0,
                empresas=[],
                mensagem=f"Nenhuma empresa encontrada com o nome '{nome}'.",
            )
        elif len(empresas) > 1:
            saida = BuscarEmpresaOutput(
                termo_buscado=nome,
                encontrada=True,
                ambigua=True,
                total_encontradas=len(empresas),
                empresas=empresas,
                mensagem=f"Ambiguidade detectada: {len(empresas)} empresas correspondem ao termo '{nome}'. Solicite confirmação.",
            )
        else:
            saida = BuscarEmpresaOutput(
                termo_buscado=nome,
                encontrada=True,
                ambigua=False,
                total_encontradas=1,
                empresas=empresas,
                mensagem="Empresa localizada com sucesso.",
            )
        return saida.model_dump()

    except httpx.TimeoutException:
        return BuscarEmpresaOutput(
            termo_buscado=nome, encontrada=False, ambigua=False, total_encontradas=0,
            empresas=[], mensagem="Erro de timeout ao consultar a API SaaS."
        ).model_dump()
    except httpx.HTTPStatusError as e:
        return BuscarEmpresaOutput(
            termo_buscado=nome, encontrada=False, ambigua=False, total_encontradas=0,
            empresas=[], mensagem=f"Erro HTTP {e.response.status_code} ao buscar empresa."
        ).model_dump()
    except Exception as e:
        return BuscarEmpresaOutput(
            termo_buscado=nome, encontrada=False, ambigua=False, total_encontradas=0,
            empresas=[], mensagem=f"Falha de comunicação com o SaaS: {str(e)}"
        ).model_dump()


class ConsultarAssinaturaInput(BaseModel):
    empresa_id: int = Field(..., gt=0, description="Identificador numérico único da empresa (empresa_id).")


class ConsultarAssinaturaOutput(BaseModel):
    empresa_id: int
    encontrada: bool
    assinatura_id: Optional[int] = None
    plano: Optional[str] = None
    status: Optional[str] = None
    saldo_creditos: Optional[int] = None
    mensagem: str


@tool(args_schema=ConsultarAssinaturaInput)
def consultar_assinatura(empresa_id: int) -> dict:
    """Consulta o status da assinatura e o saldo atual de créditos de API (GET /assinaturas/{empresa_id})."""
    url = f"{RUNTIME_CONFIG['saas_base_url']}/assinaturas/{empresa_id}"
    try:
        with httpx.Client(timeout=RUNTIME_CONFIG["timeout"]) as client:
            resp = client.get(url)
            resp.raise_for_status()
            dados = resp.json()

        assinatura = dados[0] if isinstance(dados, list) and dados else dados
        if not assinatura:
            saida = ConsultarAssinaturaOutput(
                empresa_id=empresa_id,
                encontrada=False,
                mensagem=f"Nenhuma assinatura encontrada para a empresa ID {empresa_id}.",
            )
        else:
            saida = ConsultarAssinaturaOutput(
                empresa_id=empresa_id,
                encontrada=True,
                assinatura_id=assinatura.get("id"),
                plano=assinatura.get("plano", "Padrão"),
                status=assinatura.get("status"),
                saldo_creditos=assinatura.get("saldo_creditos", 0),
                mensagem="Assinatura consultada com sucesso.",
            )
        return saida.model_dump()

    except httpx.HTTPStatusError as e:
        msg = "Assinatura não encontrada (404)." if e.response.status_code == 404 else f"Erro HTTP {e.response.status_code}."
        return ConsultarAssinaturaOutput(empresa_id=empresa_id, encontrada=False, mensagem=msg).model_dump()
    except Exception as e:
        return ConsultarAssinaturaOutput(
            empresa_id=empresa_id, encontrada=False, mensagem=f"Erro ao consultar assinatura: {str(e)}"
        ).model_dump()


class IncluirCreditosInput(BaseModel):
    assinatura_id: int = Field(..., gt=0, description="Identificador numérico da assinatura ativa (assinatura_id).")
    quantidade: int = Field(..., gt=0, description="Quantidade positiva de créditos extras a incluir (máximo 3.000).")
    motivo: str = Field(default="Bonificação operacional via CS", description="Justificativa do bônus de créditos.")


class IncluirCreditosOutput(BaseModel):
    assinatura_id: int
    aprovado: bool
    creditos_adicionados: int
    saldo_anterior: Optional[int] = None
    novo_saldo: Optional[int] = None
    mensagem: str


@tool(args_schema=IncluirCreditosInput)
def incluir_creditos(assinatura_id: int, quantidade: int, motivo: str = "Bonificação operacional via CS") -> dict:
    """Inclui créditos extras de API em uma assinatura ativa (POST /assinaturas/{id}/creditos)."""
    limite = RUNTIME_CONFIG["max_credits"]

    # Validação determinística antes da chamada HTTP
    if quantidade <= 0:
        return IncluirCreditosOutput(
            assinatura_id=assinatura_id, aprovado=False, creditos_adicionados=0,
            mensagem="Recusado: a quantidade de créditos deve ser estritamente positiva."
        ).model_dump()

    if quantidade > limite:
        return IncluirCreditosOutput(
            assinatura_id=assinatura_id, aprovado=False, creditos_adicionados=0,
            mensagem=f"Recusado: a quantidade ({quantidade}) excede o teto operacional permitido de {limite} créditos."
        ).model_dump()

    url = f"{RUNTIME_CONFIG['saas_base_url']}/assinaturas/{assinatura_id}/creditos"
    try:
        with httpx.Client(timeout=RUNTIME_CONFIG["timeout"]) as client:
            resp = client.post(url, json={"quantidade": quantidade, "motivo": motivo})
            resp.raise_for_status()
            res = resp.json()

        return IncluirCreditosOutput(
            assinatura_id=assinatura_id,
            aprovado=True,
            creditos_adicionados=quantidade,
            saldo_anterior=res.get("saldo_anterior"),
            novo_saldo=res.get("novo_saldo"),
            mensagem="Créditos extras incluídos com sucesso.",
        ).model_dump()

    except httpx.HTTPStatusError as e:
        detalhe = e.response.text
        return IncluirCreditosOutput(
            assinatura_id=assinatura_id, aprovado=False, creditos_adicionados=0,
            mensagem=f"Operação rejeitada pelo SaaS (HTTP {e.response.status_code}): {detalhe}"
        ).model_dump()
    except Exception as e:
        return IncluirCreditosOutput(
            assinatura_id=assinatura_id, aprovado=False, creditos_adicionados=0,
            mensagem=f"Falha técnica ao incluir créditos: {str(e)}"
        ).model_dump()


ferramentas = [buscar_empresa, consultar_assinatura, incluir_creditos]
