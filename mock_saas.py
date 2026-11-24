from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

mock_app = FastAPI(title="SaaS Base Simulator (Mock PostgreSQL)")

SIMULATED_FAILURE = {"enabled": False}

DB_EMPRESAS = [
    {"id": 101, "nome": "Logística Sul Transportes Ltda", "cnpj": "12.345.678/0001-90"},
    {"id": 102, "nome": "TechNova Cloud Solutions", "cnpj": "98.765.432/0001-10"},
    {"id": 103, "nome": "Grupo Horizonte Varejo", "cnpj": "11.222.333/0001-44"},
    {"id": 104, "nome": "Grupo Horizonte Indústria", "cnpj": "55.666.777/0001-88"},
]

DB_ASSINATURAS = {
    101: {"id": 5001, "empresa_id": 101, "plano": "Enterprise API", "status": "ativa", "saldo_creditos": 2000},
    102: {"id": 5002, "empresa_id": 102, "plano": "Growth API", "status": "inativa", "saldo_creditos": 150},
    103: {"id": 5003, "empresa_id": 103, "plano": "Starter API", "status": "ativa", "saldo_creditos": 500},
    104: {"id": 5004, "empresa_id": 104, "plano": "Enterprise API", "status": "ativa", "saldo_creditos": 8000},
}


class CreditoPayload(BaseModel):
    quantidade: int
    motivo: str = ""


@mock_app.post("/simulador/falha")
def toggle_falha(ativar: bool):
    SIMULATED_FAILURE["enabled"] = ativar
    return {"falha_simulada_ativa": SIMULATED_FAILURE["enabled"]}


@mock_app.get("/simulador/estado")
def ver_banco():
    return {"empresas": DB_EMPRESAS, "assinaturas": DB_ASSINATURAS}


@mock_app.get("/empresas")
def listar_empresas(nome: str = Query(..., min_length=1)):
    if SIMULATED_FAILURE["enabled"]:
        raise HTTPException(status_code=500, detail="Erro simulado de conexão com PostgreSQL.")
    termo = nome.lower()
    return [e for e in DB_EMPRESAS if termo in e["nome"].lower()]


@mock_app.get("/assinaturas/{empresa_id}")
def obter_assinatura(empresa_id: int):
    if SIMULATED_FAILURE["enabled"]:
        raise HTTPException(status_code=500, detail="Timeout simulado na consulta de assinatura.")
    assinatura = DB_ASSINATURAS.get(empresa_id)
    if not assinatura:
        raise HTTPException(status_code=404, detail="Assinatura não encontrada.")
    return assinatura


@mock_app.post("/assinaturas/{assinatura_id}/creditos")
def adicionar_creditos(assinatura_id: int, payload: CreditoPayload):
    if SIMULATED_FAILURE["enabled"]:
        raise HTTPException(status_code=500, detail="Falha ao gravar transação no banco.")
    for _, ass in DB_ASSINATURAS.items():
        if ass["id"] == assinatura_id:
            if ass["status"] != "ativa":
                raise HTTPException(status_code=422, detail="Assinatura não está ativa.")
            saldo_anterior = ass["saldo_creditos"]
            ass["saldo_creditos"] += payload.quantidade
            return {
                "assinatura_id": assinatura_id,
                "saldo_anterior": saldo_anterior,
                "creditos_adicionados": payload.quantidade,
                "novo_saldo": ass["saldo_creditos"],
                "motivo": payload.motivo,
            }
    raise HTTPException(status_code=404, detail="Assinatura ID inexistente.")
