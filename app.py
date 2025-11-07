# app.py — API de Frete com FAIXAS DE CEP (100 em 100 KM)
import os
import math
import re
from typing import Dict, Any, List, Tuple, Optional
import pandas as pd
from flask import Flask, request, Response

# ==========================
# CONFIGURAÇÕES
# ==========================
TOKEN_SECRETO = os.getenv("TOKEN_SECRETO", "teste123")

# MÚLTIPLOS CENTROS DE DISTRIBUIÇÃO
CENTROS_DISTRIBUICAO = [
    {"nome": "Frederico Westphalen-RS", "cep": "98400000", "uf": "RS"},
    {"nome": "Campo Grande-MS", "cep": "79108630", "uf": "MS"},
    {"nome": "Tauá-CE", "cep": "63660000", "uf": "CE"},
    {"nome": "Montes Claros-MG", "cep": "39404627", "uf": "MG"},
]

# CEP de origem padrão (pode ser sobrescrito por variável de ambiente)
CEP_ORIGEM_DEFAULT = os.getenv("CEP_ORIGEM", "98400000")

ARQ_PLANILHA = os.getenv("PLANILHA_FRETE", "tabela de frete atualizada(2)(Recuperado Automaticamente).xlsx")

DEFAULT_VALOR_KM = float(os.getenv("DEFAULT_VALOR_KM", "7.0"))
DEFAULT_TAM_CAMINHAO = float(os.getenv("DEFAULT_TAM_CAMINHAO", "8.5"))
DEFAULT_KM = float(os.getenv("DEFAULT_KM", "450.0"))

PALAVRAS_IGNORAR = {
    "VALOR KM", "TAMANHO CAMINHAO", "TAMANHO CAMINHÃO",
    "CALCULO DE FRETE POR TAMANHO DE PEÇA", "CÁLCULO DE FRETE POR TAMANHO DE PEÇA"
}

app = Flask(__name__)

# ==========================
# TABELA DE FAIXAS CEP -> KM PARA CADA CENTRO DE DISTRIBUIÇÃO
# ==========================

# Frederico Westphalen-RS (98400000)
FAIXAS_FREDERICO_WESTPHALEN = [
    ("98400000", "98419999", 10),    # Local
    ("98415000", "98419999", 10),
    ("98300000", "98399999", 50),
    ("98420000", "98499999", 50),
    ("99700000", "99799999", 100),
    ("98000000", "98299999", 150),
    ("99000000", "99099999", 200),
    ("95000000", "95999999", 300),
    ("97000000", "97999999", 300),
    ("93000000", "93999999", 400),
    ("92000000", "92999999", 450),
    ("94000000", "94999999", 500),
    ("90000000", "91999999", 500),
    ("96000000", "96999999", 600),
    ("89800000", "89899999", 200),   # SC
    ("89500000", "89699999", 400),
    ("89100000", "89299999", 500),
    ("89000000", "89099999", 550),
    ("88000000", "88099999", 600),
    ("88300000", "88499999", 650),
    ("88700000", "88899999", 700),
    ("85800000", "85899999", 300),   # PR
    ("85850000", "85869999", 400),
    ("87000000", "87199999", 600),
    ("86000000", "86199999", 700),
    ("84000000", "84999999", 750),
    ("83000000", "83999999", 800),
    ("80000000", "82999999", 850),
]

# Campo Grande-MS (79108630)
FAIXAS_CAMPO_GRANDE = [
    ("79100000", "79129999", 10),    # Local
    ("79000000", "79999999", 50),    # MS todo
    ("78000000", "78999999", 300),   # MT - Cuiabá
    ("76800000", "76999999", 400),   # RO - Rondônia
    ("85800000", "85899999", 500),   # PR - Cascavel
    ("85850000", "85869999", 600),   # PR - Foz do Iguaçu
    ("80000000", "82999999", 900),   # PR - Curitiba
    ("87000000", "87199999", 800),   # PR - Maringá
    ("18000000", "18999999", 700),   # SP - Interior oeste
    ("01000000", "08999999", 1000),  # SP - Capital
]

# Tauá-CE (63660000)
FAIXAS_TAUA = [
    ("63660000", "63669999", 10),    # Local
    ("63600000", "63699999", 50),    # Região
    ("60000000", "63999999", 200),   # CE todo
    ("64000000", "64999999", 250),   # PI - Piauí
    ("59000000", "59999999", 300),   # RN
    ("58000000", "58999999", 350),   # PB
    ("50000000", "56999999", 400),   # PE
    ("57000000", "57999999", 450),   # AL
    ("49000000", "49999999", 500),   # SE
    ("65000000", "65999999", 300),   # MA
    ("40000000", "48999999", 800),   # BA
    ("66000000", "68999999", 1200),  # PA
]

# Montes Claros-MG (39404627)
FAIXAS_MONTES_CLAROS = [
    ("39400000", "39419999", 10),    # Local
    ("39000000", "39999999", 100),   # Norte MG
    ("38000000", "38999999", 150),   # Norte MG
    ("30000000", "31999999", 300),   # BH
    ("32000000", "34999999", 280),   # Contagem/Betim
    ("35000000", "35999999", 250),   # Sul de Minas
    ("36000000", "36999999", 200),   # Juiz de Fora
    ("37000000", "37999999", 220),   # Sul de Minas
    ("40000000", "48999999", 400),   # BA
    ("29000000", "29999999", 500),   # ES
    ("70000000", "72999999", 600),   # DF
    ("74000000", "76999999", 650),   # GO
]

# ==========================
# FUNÇÕES AUXILIARES
# ==========================
def limpar_cep(cep: str) -> str:
    """Remove formatação e retorna 8 dígitos"""
    s = re.sub(r'\D', '', str(cep or ""))
    return s[:8].zfill(8) if s else "00000000"

def uf_por_cep(cep8: str) -> Optional[str]:
    """Retorna UF baseado na faixa de CEP"""
    UF_CEP_RANGES = [
        ("SP", "01000000", "19999999"), ("RJ", "20000000", "28999999"),
        ("ES", "29000000", "29999999"), ("MG", "30000000", "39999999"),
        ("BA", "40000000", "48999999"), ("SE", "49000000", "49999999"),
        ("PE", "50000000", "56999999"), ("AL", "57000000", "57999999"),
        ("PB", "58000000", "58999999"), ("RN", "59000000", "59999999"),
        ("CE", "60000000", "63999999"), ("PI", "64000000", "64999999"),
        ("MA", "65000000", "65999999"), ("PA", "66000000", "68899999"),
        ("AP", "68900000", "68999999"), ("AM", "69000000", "69899999"),
        ("RR", "69300000", "69399999"), ("AC", "69900000", "69999999"),
        ("DF", "70000000", "73699999"), ("GO", "72800000", "76799999"),
        ("TO", "77000000", "77999999"), ("MT", "78000000", "78899999"),
        ("MS", "79000000", "79999999"), ("PR", "80000000", "87999999"),
        ("SC", "88000000", "89999999"), ("RS", "90000000", "99999999"),
    ]
    try:
        n = int(cep8)
    except:
        return None
    for uf, a, b in UF_CEP_RANGES:
        if int(a) <= n <= int(b):
            return uf
    return None

def buscar_km_por_cep_e_origem(cep_origem: str, cep_destino: str) -> Tuple[float, str, str]:
    """
    Busca KM baseado no CEP de origem e destino
    Retorna: (km, fonte, centro_distribuicao)
    """
    cep_dest = limpar_cep(cep_destino)
    cep_dest_num = int(cep_dest)
    
    # Identifica qual centro de distribuição está sendo usado
    cep_orig_limpo = limpar_cep(cep_origem)
    centro_nome = "Desconhecido"
    
    for centro in CENTROS_DISTRIBUICAO:
        if limpar_cep(centro["cep"]) == cep_orig_limpo:
            centro_nome = centro["nome"]
            break
    
    # Seleciona a tabela de faixas correta
    faixas = []
    if cep_orig_limpo == "98400000":
        faixas = FAIXAS_FREDERICO_WESTPHALEN
    elif cep_orig_limpo == "79108630":
        faixas = FAIXAS_CAMPO_GRANDE
    elif cep_orig_limpo == "63660000":
        faixas = FAIXAS_TAUA
    elif cep_orig_limpo == "39404627":
        faixas = FAIXAS_MONTES_CLAROS
    
    # Busca na tabela específica
    for cep_ini, cep_fim, km in faixas:
        if int(cep_ini) <= cep_dest_num <= int(cep_fim):
            return (float(km), f"faixa_{centro_nome}", centro_nome)
    
    # Fallback por UF
    uf = uf_por_cep(cep_dest)
    if uf:
        km_uf = {
            "RS": 150, "SC": 450, "PR": 700, "SP": 1100, "RJ": 1500,
            "MG": 1600, "ES": 1800, "MS": 1600, "MT": 2200, "DF": 2000,
            "GO": 2100, "TO": 2500, "BA": 2600, "SE": 2700, "AL": 2800,
            "PE": 3000, "PB": 3100, "RN": 3200, "CE": 3400, "PI": 3300,
            "MA": 3500, "PA": 3800, "AP": 4100, "AM": 4200, "RO": 4000,
            "AC": 4300, "RR": 4500,
        }
        return (float(km_uf.get(uf, DEFAULT_KM)), f"uf_{uf}", centro_nome)
    
    return (DEFAULT_KM, "default", centro_nome)

def escolher_melhor_origem(cep_destino: str) -> Tuple[str, float, str]:
    """
    Escolhe o centro de distribuição mais próximo do destino
    Retorna: (cep_origem, km, nome_centro)
    """
    melhor_km = float('inf')
    melhor_origem = CENTROS_DISTRIBUICAO[0]["cep"]
    melhor_centro = CENTROS_DISTRIBUICAO[0]["nome"]
    melhor_fonte = "default"
    
    for centro in CENTROS_DISTRIBUICAO:
        km, fonte, nome = buscar_km_por_cep_e_origem(centro["cep"], cep_destino)
        if km < melhor_km:
            melhor_km = km
            melhor_origem = centro["cep"]
            melhor_centro = nome
            melhor_fonte = fonte
    
    return (melhor_origem, melhor_km, melhor_centro)

# ==========================
# FUNÇÕES DA PLANILHA
# ==========================
def limpar_texto(nome: Any) -> str:
    if not isinstance(nome, str):
        return ""
    return " ".join(nome.replace("\n", " ").split()).strip()

def extrai_numero_linha(row) -> Optional[float]:
    for v in row:
        if v is None or pd.isna(v):
            continue
        s = str(v).strip().upper()
        if s in ("", "NAN", "NONE", "NULL"):
            continue
        s = s.replace(",", ".")
        s = re.sub(r'(METROS?|KM|R\$|REAIS|/KM)', '', s, flags=re.IGNORECASE).strip()
        try:
            f = float(s)
            if math.isfinite(f) and f > 0:
                return f
        except:
            pass
    return None

def carregar_constantes(xls: pd.ExcelFile) -> Dict[str, float]:
    valor_km = DEFAULT_VALOR_KM
    tam_caminhao = DEFAULT_TAM_CAMINHAO
    
    for aba in ("BASE_CALCULO", "D", "BASE", "CONSTANTES"):
        if aba not in xls.sheet_names:
            continue
        try:
            raw = pd.read_excel(xls, aba, header=None)
            for _, row in raw.iterrows():
                texto = " ".join([str(v).upper() for v in row if isinstance(v, str)])
                if "VALOR" in texto or "KM" in texto:
                    num = extrai_numero_linha(row)
                    if num and 3 <= num <= 50:
                        valor_km = num
                if "TAMANHO" in texto and "CAMINH" in texto:
                    num = extrai_numero_linha(row)
                    if num and 3 <= num <= 20:
                        tam_caminhao = num
        except:
            pass
    
    return {"VALOR_KM": valor_km, "TAM_CAMINHAO": tam_caminhao}

def carregar_cadastro_produtos(xls: pd.ExcelFile) -> pd.DataFrame:
    for aba in ("CADASTRO_PRODUTO", "CADASTRO", "PRODUTOS"):
        if aba not in xls.sheet_names:
            continue
        try:
            raw = pd.read_excel(xls, aba, header=None)
            nome_col = 2 if raw.shape[1] > 2 else 0
            dim1_col = 3 if raw.shape[1] > 3 else (1 if raw.shape[1] > 1 else 0)
            dim2_col = 4 if raw.shape[1] > 4 else (2 if raw.shape[1] > 2 else 1)
            
            df = raw[[nome_col, dim1_col, dim2_col]].copy()
            df.columns = ["nome", "dim1", "dim2"]
            df["nome"] = df["nome"].apply(limpar_texto)
            df = df[~df["nome"].str.upper().isin(PALAVRAS_IGNORAR)]
            df = df[df["nome"].astype(str).str.len() > 0]
            df["dim1"] = pd.to_numeric(df["dim1"], errors="coerce").fillna(0.0)
            df["dim2"] = pd.to_numeric(df["dim2"], errors="coerce").fillna(0.0)
            df = df.drop_duplicates(subset=["nome"], keep="first").reset_index(drop=True)
            return df[["nome", "dim1", "dim2"]]
        except:
            pass
    
    return pd.DataFrame(columns=["nome", "dim1", "dim2"])

def tipo_produto(nome: str) -> str:
    n = (nome or "").lower()
    if "fossa" in n:
        return "fossa"
    if "vertical" in n:
        return "vertical"
    if "horizontal" in n:
        return "horizontal"
    if "tc" in n and ("10.000" in n or "10000" in n or "10.0" in n):
        return "tc_ate_10k"
    return "auto"

def tamanho_peca_por_nome(nome: str, dim1: float, dim2: float) -> float:
    t = tipo_produto(nome)
    if t in ("fossa", "vertical"):
        return float(dim1 or 0.0)
    if t in ("horizontal", "tc_ate_10k"):
        return float(dim2 or 0.0)
    return float(max(float(dim1 or 0.0), float(dim2 or 0.0)))

def montar_catalogo_tamanho(df: pd.DataFrame) -> Dict[str, float]:
    mapa = {}
    for _, r in df.iterrows():
        try:
            nome = limpar_texto(r["nome"])
            if not nome or nome.upper() in PALAVRAS_IGNORAR:
                continue
            tam = tamanho_peca_por_nome(nome, float(r["dim1"]), float(r["dim2"]))
            if tam > 0:
                mapa[nome] = tam
        except:
            pass
    return mapa

def carregar_tudo() -> Dict[str, Any]:
    try:
        xls = pd.ExcelFile(ARQ_PLANILHA)
        consts = carregar_constantes(xls)
        cadastro = carregar_cadastro_produtos(xls)
        catalogo = montar_catalogo_tamanho(cadastro)
        print(f"[OK] Planilha carregada: {len(catalogo)} produtos")
        return {"consts": consts, "catalogo": catalogo}
    except Exception as e:
        print(f"[WARN] Planilha não encontrada: {e}")
        return {
            "consts": {"VALOR_KM": DEFAULT_VALOR_KM, "TAM_CAMINHAO": DEFAULT_TAM_CAMINHAO},
            "catalogo": {}
        }

DATA = carregar_tudo()

# ==========================
# CÁLCULO DE FRETE
# ==========================
def calcula_valor_item(tamanho_peca_m: float, km: float, valor_km: float, tam_caminhao: float) -> float:
    """Fórmula: (tamanho_peça / tamanho_caminhão) * valor_km * km"""
    if tamanho_peca_m <= 0 or tam_caminhao <= 0:
        return 0.0
    ocupacao = float(tamanho_peca_m) / float(tam_caminhao)
    return round(float(valor_km) * float(km) * ocupacao, 2)

def parse_prods(prods_str: str) -> List[Dict[str, Any]]:
    """Parse dos produtos no formato Tray"""
    itens = []
    if not prods_str:
        return itens
    
    # Tray pode enviar com / ou |
    blocos = []
    for sep in ("/", "|"):
        if sep in prods_str:
            blocos = [b for b in prods_str.split(sep) if b.strip()]
            break
    if not blocos:
        blocos = [prods_str]

    def norm_num(x):
        if x is None:
            return 0.0
        s = str(x).strip().lower()
        if s in ("", "null", "none", "nan"):
            return 0.0
        s = s.replace(",", ".")
        try:
            return float(s)
        except:
            return 0.0

    def cm_to_m(x):
        """Converte cm para metros se necessário"""
        if not x or x == 0:
            return 0.0
        # Se maior que 20, assume que está em cm
        return x / 100.0 if x > 20 else x

    for raw in blocos:
        try:
            partes = raw.split(";")
            if len(partes) < 8:
                print(f"[WARN] Item com menos de 8 campos: {raw}")
                continue
            
            comp_raw, larg_raw, alt_raw, cub, qty, peso, codigo, valor = partes[:8]
            
            comp = cm_to_m(norm_num(comp_raw))
            larg = cm_to_m(norm_num(larg_raw))
            alt = cm_to_m(norm_num(alt_raw))
            
            print(f"[DEBUG] Parse: comp={comp_raw}->{comp:.2f}m, larg={larg_raw}->{larg:.2f}m, alt={alt_raw}->{alt:.2f}m")
            
            item = {
                "comp": comp,
                "larg": larg,
                "alt": alt,
                "cub": norm_num(cub),
                "qty": int(norm_num(qty)) if norm_num(qty) > 0 else 1,
                "peso": norm_num(peso),
                "codigo": (codigo or "").strip(),
                "valor": norm_num(valor),
            }
            itens.append(item)
        except Exception as e:
            print(f"[ERROR] Erro parse item: {raw} - {e}")
    
    return itens

# ==========================
# ENDPOINTS
# ==========================
@app.route("/", methods=["GET", "POST"])
def index():
    """Endpoint principal - redireciona para cálculo de frete se tiver parâmetros"""
    # Se vier com parâmetros da Tray, processa como frete
    if request.args.get("cep_destino") or request.args.get("prods"):
        return frete()
    
    return {
        "api": "Bakof Frete",
        "versao": "4.0 - Faixas de CEP",
        "endpoints": {
            "/health": "Status da API",
            "/frete": "Calcular frete",
            "/": "Calcular frete (compatível Tray)",
            "/consultar-cep": "Consultar KM de um CEP"
        }
    }

@app.route("/health")
def health():
    return {
        "ok": True,
        "centros_distribuicao": [
            {"nome": cd["nome"], "cep": cd["cep"], "uf": cd["uf"]} 
            for cd in CENTROS_DISTRIBUICAO
        ],
        "valores": DATA["consts"],
        "produtos_catalogo": len(DATA["catalogo"]),
    }

@app.route("/consultar-cep")
def consultar_cep():
    """Endpoint para consultar KM de um CEP específico"""
    cep = request.args.get("cep", "")
    origem = request.args.get("origem", "")  # Origem específica (opcional)
    
    if not cep:
        return {"erro": "Informe o parâmetro 'cep'"}
    
    if origem:
        # Consulta com origem específica
        km, fonte, centro = buscar_km_por_cep_e_origem(origem, cep)
        cep_origem = origem
    else:
        # Escolhe melhor origem automaticamente
        cep_origem, km, centro = escolher_melhor_origem(cep)
        fonte = f"auto_{centro}"
    
    uf = uf_por_cep(limpar_cep(cep))
    
    return {
        "cep_destino": limpar_cep(cep),
        "uf": uf,
        "centro_distribuicao": centro,
        "cep_origem": cep_origem,
        "km": km,
        "fonte": fonte
    }

@app.route("/frete", methods=["GET", "POST"])
def frete():
    """Endpoint de cálculo de frete - compatível com Tray"""
    # Autenticação (opcional - Tray não envia token sempre)
    token = request.args.get("token", "")
    # Permite acesso sem token OU com token correto
    if token and token != TOKEN_SECRETO:
        return Response("Token inválido", status=403)

    # Parâmetros
    cep_destino = request.args.get("cep_destino", "")
    prods = request.args.get("prods", "")
    cep_origem_param = request.args.get("cep_origem", "")  # Origem específica (opcional)

    # Log para debug
    print(f"[DEBUG] CEP Destino: {cep_destino}")
    print(f"[DEBUG] CEP Origem (param): {cep_origem_param}")
    print(f"[DEBUG] Produtos: {prods}")

    if not cep_destino:
        return Response("Parâmetro 'cep_destino' obrigatório", status=400)
    
    if not prods:
        return Response("Parâmetro 'prods' obrigatório", status=400)

    # Parse produtos
    itens = parse_prods(prods)
    print(f"[DEBUG] Itens parseados: {len(itens)}")
    
    if not itens:
        return Response("Nenhum item válido em 'prods'", status=400)

    # Constantes base
    valor_km = DATA["consts"].get("VALOR_KM", DEFAULT_VALOR_KM)
    tam_caminhao = DATA["consts"].get("TAM_CAMINHAO", DEFAULT_TAM_CAMINHAO)

    # Permite override via parâmetro
    try:
        if request.args.get("valor_km"):
            valor_km = float(str(request.args["valor_km"]).replace(",", "."))
        if request.args.get("tam_caminhao"):
            tam_caminhao = float(str(request.args["tam_caminhao"]).replace(",", "."))
    except:
        pass

    # Escolhe a melhor origem automaticamente (mais próxima)
    if cep_origem_param:
        # Se veio origem específica, usa ela
        cep_origem_usado = limpar_cep(cep_origem_param)
        km, km_fonte, centro_nome = buscar_km_por_cep_e_origem(cep_origem_usado, cep_destino)
    else:
        # Escolhe automaticamente o CD mais próximo
        cep_origem_usado, km, centro_nome = escolher_melhor_origem(cep_destino)
        km_fonte = f"auto_{centro_nome}"
    
    print(f"[DEBUG] Origem escolhida: {centro_nome} ({cep_origem_usado})")
    print(f"[DEBUG] KM calculado: {km} ({km_fonte})")

    # Calcula frete por produto
    total = 0.0
    itens_xml = []
    
    for it in itens:
        nome = it["codigo"] or "Item"
        
        # Busca tamanho no catálogo
        tam_catalogo = DATA["catalogo"].get(nome)
        if tam_catalogo is None:
            # Usa a maior dimensão do produto
            tam_catalogo = max(it["comp"], it["larg"], it["alt"])
            # Se não tem dimensões, usa diâmetro padrão de 2m
            if tam_catalogo == 0:
                tam_catalogo = 2.0
        
        print(f"[DEBUG] Produto: {nome}, Tamanho: {tam_catalogo:.3f}m")
        
        # Calcula valores
        v_unit = calcula_valor_item(tam_catalogo, km, valor_km, tam_caminhao)
        v_tot = v_unit * max(1, it["qty"])
        total += v_tot
        
        print(f"[DEBUG] Valor unitário: R$ {v_unit:.2f}, Total: R$ {v_tot:.2f}")
        
        itens_xml.append(f"""
      <item>
        <codigo>{nome}</codigo>
        <quantidade>{it['qty']}</quantidade>
        <tamanho_metros>{tam_catalogo:.3f}</tamanho_metros>
        <valor_unitario>{v_unit:.2f}</valor_unitario>
        <valor_total>{v_tot:.2f}</valor_total>
      </item>""")

    print(f"[DEBUG] VALOR TOTAL: R$ {total:.2f}")

    # Monta resposta XML (formato Tray)
    uf = uf_por_cep(limpar_cep(cep_destino))
    
    xml = f"""<?xml version="1.0"?>
<cotacao>
  <resultado>
    <codigo>BAKOF</codigo>
    <transportadora>Bakof Logistica</transportadora>
    <servico>Transporte Rodoviario</servico>
    <transporte>TERRESTRE</transporte>
    <valor>{total:.2f}</valor>
    <prazo_min>4</prazo_min>
    <prazo_max>7</prazo_max>
    <entrega_domiciliar>1</entrega_domiciliar>
    <detalhes>
      <origem>{centro_nome}</origem>
      <cep_origem>{cep_origem_usado}</cep_origem>
      <km>{km:.1f}</km>
      <uf_destino>{uf or 'N/A'}</uf_destino>
      <fonte_km>{km_fonte}</fonte_km>
      <valor_km>{valor_km:.2f}</valor_km>
      <itens>{"".join(itens_xml)}
      </itens>
    </detalhes>
  </resultado>
</cotacao>"""
    
    return Response(xml, mimetype="application/xml")

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    print("=" * 70)
    print("🚀 API de Frete Bakof - Múltiplos Centros de Distribuição")
    print("=" * 70)
    print("📍 Centros de Distribuição:")
    for cd in CENTROS_DISTRIBUICAO:
        print(f"   • {cd['nome']} ({cd['uf']}) - CEP {cd['cep']}")
    print(f"\n🔑 Token: {TOKEN_SECRETO}")
    print(f"📊 Produtos: {len(DATA['catalogo'])}")
    print(f"💰 Valor/KM: R$ {DATA['consts']['VALOR_KM']:.2f}")
    print(f"🚛 Tamanho caminhão: {DATA['consts']['TAM_CAMINHAO']:.1f}m")
    print(f"🌐 Servidor: http://0.0.0.0:{port}")
    print(f"\n✨ Sistema escolhe automaticamente o CD mais próximo!")
    print("=" * 70)
    app.run(host="0.0.0.0", port=port, debug=False)
