from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from langchain_core.messages import HumanMessage

load_dotenv()

from agent.state import AgentRequest, AgentResponse
from agent.graph import app as langgraph_app
from agent.tools import RUNTIME_CONFIG

api = FastAPI(
    title="CS-CreditGuard AI | API do Agente (FastAPI + LangGraph)",
    description="API REST para consulta de assinaturas e inclusão segura de créditos B2B.",
    version="1.0.0",
)


@api.get("/health")
def health_check():
    return {"status": "online", "config_atual": RUNTIME_CONFIG}


@api.post("/config")
def atualizar_configuracao(saas_url: str, max_credits: int = 3000, timeout: float = 10.0):
    """Ajusta dinamicamente os parâmetros operacionais da FastAPI via Streamlit ou Swagger."""
    RUNTIME_CONFIG["saas_base_url"] = saas_url.rstrip("/")
    RUNTIME_CONFIG["max_credits"] = max_credits
    RUNTIME_CONFIG["timeout"] = timeout
    return {"mensagem": "Configurações aplicadas com sucesso.", "config_atual": RUNTIME_CONFIG}


@api.post("/agent/executar", response_model=AgentResponse)
def executar_agente(req: AgentRequest):
    """Recebe instrução em linguagem natural, executa o StateGraph e retorna resposta JSON estruturada."""
    if req.saas_url_override:
        RUNTIME_CONFIG["saas_base_url"] = req.saas_url_override.rstrip("/")
    if req.limite_creditos_override:
        RUNTIME_CONFIG["max_credits"] = req.limite_creditos_override

    estado_inicial = {
        "messages": [HumanMessage(content=req.instrucao)],
        "empresa_id": None,
        "empresa_nome": None,
        "assinatura_id": None,
        "status_assinatura": None,
        "saldo_atual": None,
        "creditos_solicitados": None,
        "iteracoes": 0,
        "max_iteracoes": req.max_iteracoes_override or 6,
        "limite_creditos": RUNTIME_CONFIG["max_credits"],
    }

    try:
        resultado = langgraph_app.invoke(
            estado_inicial,
            config={"recursion_limit": (req.max_iteracoes_override or 6) * 3 + 2},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro na execução do LangGraph: {str(e)}")

    parecer = resultado["messages"][-1].content

    if "Aprovada" in parecer:
        status_op = "SUCESSO"
    elif "Esclarecimento" in parecer or "Ambiguidade" in parecer:
        status_op = "AMBIGUIDADE"
    elif "Recusada" in parecer:
        status_op = "RECUSADO"
    else:
        status_op = "CONSULTA"

    return AgentResponse(
        status=status_op,
        parecer_agente=parecer,
        dados_operacionais={
            "empresa_id": resultado.get("empresa_id"),
            "empresa_nome": resultado.get("empresa_nome"),
            "assinatura_id": resultado.get("assinatura_id"),
            "status_assinatura": resultado.get("status_assinatura"),
            "saldo_anterior": resultado.get("saldo_atual"),
            "creditos_solicitados": resultado.get("creditos_solicitados"),
        },
        iteracoes_executadas=resultado.get("iteracoes", 0),
    )
