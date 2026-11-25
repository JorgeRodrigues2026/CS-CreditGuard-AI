import os
import json
from typing import Literal
from dotenv import load_dotenv

from langchain_groq import ChatGroq
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode

from agent.state import EstadoAgente
from agent.tools import ferramentas
from agent.prompts import build_system_prompt

load_dotenv()

# 3. CONFIGURAÇÃO DO MODELO E PROMPT (Padrão agente2.py)
MODEL_NAME = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
llm = ChatGroq(model=MODEL_NAME, temperature=0.0)
llm_com_tools = llm.bind_tools(ferramentas)


# 4. DEFINIÇÃO DOS NÓS (NODES)
def no_agente(state: EstadoAgente):
    """Nó que invoca o LLM com o histórico atual e controla o limite de iterações."""
    iteracao_atual = state.get("iteracoes", 0) + 1
    max_iter = state.get("max_iteracoes", 6)

    if iteracao_atual > max_iter:
        aviso = AIMessage(
            content="- **Status da Operação:** Recusada\n- **Motivo:** Limite máximo de iterações atingido por segurança operacional."
        )
        return {"messages": [aviso], "iteracoes": iteracao_atual}

    system_prompt = build_system_prompt(state.get("limite_creditos", 3000))
    mensagens_completas = [system_prompt] + state["messages"]
    resposta = llm_com_tools.invoke(mensagens_completas)
    return {"messages": [resposta], "iteracoes": iteracao_atual}


# ToolNode é um nó pré-construído do LangGraph que executa as tools chamadas pelo LLM
no_ferramentas = ToolNode(ferramentas)


def no_sincronizar_estado(state: EstadoAgente):
    """Extrai os retornos estruturados das ferramentas para manter os metadados no State."""
    updates = {}
    for msg in reversed(state["messages"]):
        if not isinstance(msg, ToolMessage):
            break
        try:
            payload = json.loads(msg.content) if isinstance(msg.content, str) else msg.content
        except Exception:
            continue

        if msg.name == "buscar_empresa" and payload.get("encontrada") and not payload.get("ambigua"):
            emp = payload["empresas"][0]
            updates["empresa_id"] = emp.get("id")
            updates["empresa_nome"] = emp.get("nome")

        elif msg.name == "consultar_assinatura" and payload.get("encontrada"):
            updates["assinatura_id"] = payload.get("assinatura_id")
            updates["status_assinatura"] = payload.get("status")
            updates["saldo_atual"] = payload.get("saldo_creditos")

        elif msg.name == "incluir_creditos":
            updates["creditos_solicitados"] = payload.get("creditos_adicionados")
            if payload.get("saldo_anterior") is not None:
                updates["saldo_atual"] = payload.get("saldo_anterior")

    return updates


# 5. DEFINIÇÃO DAS TRANSIÇÕES (CONDITIONAL EDGES)
def decidir_proximo_passo(state: EstadoAgente) -> Literal["ferramentas", "__end__"]:
    """Verifica se a última mensagem do agente contém pedido de chamada de ferramenta."""
    if state.get("iteracoes", 0) >= state.get("max_iteracoes", 6):
        return "__end__"
    ultima_mensagem = state["messages"][-1]
    if hasattr(ultima_mensagem, "tool_calls") and ultima_mensagem.tool_calls:
        return "ferramentas"
    return "__end__"


# 6. MONTAGEM E COMPILAÇÃO DO GRAFO
workflow = StateGraph(EstadoAgente)

workflow.add_node("agente", no_agente)
workflow.add_node("ferramentas", no_ferramentas)
workflow.add_node("sincronizar_estado", no_sincronizar_estado)

workflow.add_edge(START, "agente")
workflow.add_conditional_edges("agente", decidir_proximo_passo)
workflow.add_edge("ferramentas", "sincronizar_estado")
workflow.add_edge("sincronizar_estado", "agente")  # Loop: após rodar a tool e atualizar o estado, volta para o agente

app = workflow.compile()
