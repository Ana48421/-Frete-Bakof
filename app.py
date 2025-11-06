# app.py — FRETE por FAIXAS de CEP + Diâmetro Produto (sem chamadas externas)
import os, math, re
from typing import Dict, Any, List, Tuple, Optional
import pandas as pd
from flask import Flask, request, Response

# ==========================
# CONFIG
# ==========================
TOKEN_SECRETO = os.getenv("TOKEN_SECRETO", "teste123")
CEP_ORIGEM = os.getenv("CEP_ORIGEM", "98400000")  # Frederico Westphalen/RS - CONFIGURE SEU CEP
ARQ_PLANILHA = os.getenv("PLANILHA_FRETE", "tabela de frete atualizada(2)(Recuperado Automaticamente).xlsx")

DEFAULT_VALOR_KM = float(os.getenv("DEFAULT_VALOR_KM", "7.0"))
DEFAULT_TAM_CAMINHAO = float(os.getenv("DEFAULT_TAM_CAMINHAO", "8.5"))
DEFAULT_KM = float(os.getenv("DEFAULT_KM", "450.0"))

PALAVRAS_IGNORAR = {
    "VALOR KM","TAMANHO CAMINHAO","TAMANHO CAMINHÃO",
    "CALCULO DE FRETE POR TAMANHO DE PEÇA","CÁLCULO DE FRETE POR TAMANHO DE PEÇA"
}

# Tabela de FAIXAS de CEP -> KM estimado (edite os KM conforme sua política)
# Observação: comparação é numérica; use 8 dígitos.
CEP_FAIXAS_KM: List[Tuple[str, str, float, str]] = [
    # RS
    ("98400000", "98419999",  25.0, "FREDERICO WESTPHALEN-RS"),
    ("90000000", "91999999", 430.0, "PORTO ALEGRE-RS"),
    ("95000000", "95130999", 300.0, "CAXIAS DO SUL-RS"),
    ("96000000", "96099999", 560.0, "PELOTAS-RS"),
    ("92000000", "92999999", 420.0, "CANOAS-RS"),
    ("97000000", "97119999", 300.0, "SANTA MARIA-RS"),
    ("99000000", "99099999",  80.0, "PASSO FUNDO-RS"),
    ("99700000", "99799999", 110.0, "ERECHIM-RS"),

    # SC
    ("88000000", "88099999", 720.0, "FLORIANÓPOLIS-SC"),
    ("89200000", "89239999", 830.0, "JOINVILLE-SC"),
    ("89000000", "89099999", 780.0, "BLUMENAU-SC"),
    ("89800000", "89879999", 160.0, "CHAPECÓ-SC"),

    # PR
    ("80000000", "82999999", 1000.0, "CURITIBA-PR"),
    ("86000000", "86199999",  900.0, "LONDRINA-PR"),
    ("87000000", "87099999",  950.0, "MARINGÁ-PR"),
    ("85800000", "85879999",  520.0, "CASCAVEL-PR"),
    ("85850000", "85869999",  660.0, "FOZ DO IGUAÇU-PR"),

    # SP
    ("01000000", "05999999", 1300.0, "SÃO PAULO-SP"),
    ("07000000", "07399999", 1310.0, "GUARULHOS-SP"),
    ("13000000", "13149999", 1400.0, "CAMPINAS-SP"),
    ("09700000", "09899999", 1310.0, "SÃO BERNARDO DO CAMPO-SP"),
    ("11000000", "11999999", 1360.0, "SANTOS-SP"),
    ("12200000", "12249999", 1250.0, "SÃO JOSÉ DOS CAMPOS-SP"),
    ("14000000", "14109999", 1450.0, "RIBEIRÃO PRETO-SP"),

    # RJ
    ("20000000", "23799999", 1600.0, "RIO DE JANEIRO-RJ"),
    ("24000000", "24999999", 1610.0, "NITERÓI-RJ"),

    # MG
    ("30000000", "31999999", 1700.0, "BELO HORIZONTE-MG"),
    ("32000000", "32999999", 1700.0, "CONTAGEM-MG"),

    # DF
    ("70000000", "72799999", 2000.0, "BRASÍLIA-DF"),
]

app = Flask(__name__)

# ==========================
# HELPERS ORIGINAIS
# ==========================
def limpar_texto(nome: Any) -> str:
    if not isinstance(nome, str): return ""
    return " ".join(nome.replace("\n"," ").split()).strip()

def so_digitos(cep: Any) -> str:
    s = re.sub(r"\D","", str(cep or ""))
    return s[:8] if len(s) >= 8 else s.zfill(8)

def uf_por_cep(cep8: str) -> Optional[str]:
    UF_CEP_RANGES = [
        ("SP","01000000","19999999"),("RJ","20000000","28999999"),
        ("ES","29000000","29999999"),("MG","30000000","39999999"),
        ("BA","40000000","48999999"),("SE","49000000","49999999"),
        ("PE","50000000","56999999"),("AL","57000000","57999999"),
        ("PB","58000000","58999999"),("RN","59000000","59999999"),
        ("CE","60000000","63999999"),("PI","64000000","64999999"),
        ("MA","65000000","65999999"),("PA","66000000","68899999"),
        ("AP","68900000","68999999"),("AM","69000000","69899999"),
        ("RR","69300000","69399999"),("AC","69900000","69999999"),
        ("DF","70000000","73699999"),("GO","72800000","76799999"),
        ("TO","77000000","77999999"),("MT","78000000","78899999"),
        ("MS","79000000","79999999"),("PR","80000000","87999999"),
        ("SC","88000000","89999999"),("RS","90000000","99999999"),
    ]
    try: n = int(cep8)
    except: return None
    for uf, a, b in UF_CEP_RANGES:
        if int(a) <= n <= int(b): return uf
    return None

def extrai_numero_linha(row) -> Optional[float]:
    for v in row:
        if v is None or pd.isna(v): continue
        s = str(v).strip().upper()
        if s in ("", "NAN", "NONE", "NULL"): continue
        s = s.replace(",", ".")
        s = re.sub(r'(METROS?|KM|R\$|REAIS|/KM)', '', s, flags=re.IGNORECASE).strip()
        try:
            f = float(s)
            if math.isfinite(f) and f > 0: return f
        except: pass
    return None

# ==========================
# PLANILHA (mantido igual)
# ==========================
def carregar_constantes(xls: pd.ExcelFile) -> Dict[str, float]:
    valor_km = DEFAULT_VALOR_KM
    tam_caminhao = DEFAULT_TAM_CAMINHAO
    for aba in ("BASE_CALCULO","D","BASE","CONSTANTES"):
        if aba not in xls.sheet_names: continue
        try:
            raw = pd.read_excel(xls, aba, header=None)
            for _, row in raw.iterrows():
                texto = " ".join([str(v).upper() for v in row if isinstance(v, str)])
                if "VALOR" in texto or "KM" in texto:
                    num = extrai_numero_linha(row)
                    if num and 3 <= num <= 50: valor_km = num
                if "TAMANHO" in texto and "CAMINH" in texto:
                    num = extrai_numero_linha(row)
                    if num and 3 <= num <= 20: tam_caminhao = num
        except: pass
    return {"VALOR_KM": valor_km, "TAM_CAMINHAO": tam_caminhao}

def carregar_cadastro_produtos(xls: pd.ExcelFile) -> pd.DataFrame:
    for aba in ("CADASTRO_PRODUTO","CADASTRO","PRODUTOS"):
        if aba not in xls.sheet_names: continue
        try:
            raw = pd.read_excel(xls, aba, header=None)
            nome_col = 2 if raw.shape[1] > 2 else 0
            dim1_col = 3 if raw.shape[1] > 3 else (1 if raw.shape[1] > 1 else 0)
            dim2_col = 4 if raw.shape[1] > 4 else (2 if raw.shape[1] > 2 else 1)
            df = raw[[nome_col, dim1_col, dim2_col]].copy()
            df.columns = ["nome","dim1","dim2"]
            df["nome"] = df["nome"].apply(limpar_texto)
            df = df[~df["nome"].str.upper().isin(PALAVRAS_IGNORAR)]
            df = df[df["nome"].astype(str).str.len() > 0]
            df["dim1"] = pd.to_numeric(df["dim1"], errors="coerce").fillna(0.0)
            df["dim2"] = pd.to_numeric(df["dim2"], errors="coerce").fillna(0.0)
            df = df.drop_duplicates(subset=["nome"], keep="first").reset_index(drop=True)
            return df[["nome","dim1","dim2"]]
        except: pass
    return pd.DataFrame(columns=["nome","dim1","dim2"])

def tipo_produto(nome: str) -> str:
    n = (nome or "").lower()
    if "fossa" in n: return "fossa"
    if "vertical" in n: return "vertical"
    if "horizontal" in n: return "horizontal"
    if "tc" in n and ("10.000" in n or "10000" in n or "10.0" in n): return "tc_ate_10k"
    return "auto"

def tamanho_peca_por_nome(nome: str, dim1: float, dim2: float) -> float:
    t = tipo_produto(nome)
    if t in ("fossa","vertical"):  return float(dim1 or 0.0)
    if t in ("horizontal","tc_ate_10k"): return float(dim2 or 0.0)
    return float(max(float(dim1 or 0.0), float(dim2 or 0.0)))

def montar_catalogo_tamanho(df: pd.DataFrame) -> Dict[str, float]:
    mapa: Dict[str,float] = {}
    for _, r in df.iterrows():
        try:
            nome = limpar_texto(r["nome"])
            if not nome or nome.upper() in PALAVRAS_IGNORAR: continue
            tam = tamanho_peca_por_nome(nome, float(r["dim1"]), float(r["dim2"]))
            if tam > 0: mapa[nome] = tam
        except: pass
    return mapa

def carregar_regras_municipio(xls: pd.ExcelFile) -> List[Dict[str, Any]]:
    """(Mantido) – sem uso nesta versão por faixa"""
    if "REGRAS_MUNICIPIO" not in xls.sheet_names: return []
    return []

# ==========================
# CARREGAMENTO
# ==========================
def carregar_tudo() -> Dict[str, Any]:
    try:
        xls = pd.ExcelFile(ARQ_PLANILHA)
    except Exception as e:
        print(f"[WARN] Não foi possível carregar planilha: {e}")
        return {
            "consts": {"VALOR_KM": DEFAULT_VALOR_KM, "TAM_CAMINHAO": DEFAULT_TAM_CAMINHAO},
            "catalogo": {},
            "regras_municipio": []
        }

    consts = carregar_constantes(xls)
    cadastro = carregar_cadastro_produtos(xls)
    catalogo = montar_catalogo_tamanho(cadastro)
    regras_mun = carregar_regras_municipio(xls)
    
    return {
        "consts": consts,
        "catalogo": catalogo,
        "regras_municipio": regras_mun
    }

DATA = carregar_tudo()

# ==========================
# NOVO: CÁLCULO DE KM POR FAIXA DE CEP
# ==========================
def km_por_faixa(cep_destino: str) -> Tuple[float, str]:
    """
    Retorna (km, label_faixa). Se não encontrar, usa DEFAULT_KM.
    """
    cep8 = so_digitos(cep_destino)
    try:
        n = int(cep8)
    except:
        return (DEFAULT_KM, "default")

    for ini, fim, km, label in CEP_FAIXAS_KM:
        try:
            a = int(ini); b = int(fim)
            if a <= n <= b:
                return (float(km), label)
        except:
            continue
    return (DEFAULT_KM, "default")

# ==========================
# CÁLCULO DE FRETE
# ==========================
def calcula_valor_item(tamanho_peca_m: float, km: float, valor_km: float, tam_caminhao: float) -> float:
    """
    Fórmula: (tamanho_peça / tamanho_caminhão) * valor_km * km
    """
    if tamanho_peca_m <= 0 or tam_caminhao <= 0: return 0.0
    ocupacao = float(tamanho_peca_m) / float(tam_caminhao)
    return round(float(valor_km) * float(km) * ocupacao, 2)

def parse_prods(prods_str: str) -> List[Dict[str, Any]]:
    """Parse dos produtos no formato Tray"""
    itens: List[Dict[str, Any]] = []
    if not prods_str: return itens
    
    blocos = []
    for sep in ("/", "|"):
        if sep in prods_str:
            blocos = [b for b in prods_str.split(sep) if b.strip()]
            break
    if not blocos: blocos = [prods_str]

    def norm_num(x):
        if x is None: return 0.0
        s = str(x).strip().lower()
        if s in ("", "null", "none", "nan"): return 0.0
        s = s.replace(",", ".")
        try: return float(s)
        except: return 0.0

    def cm_to_m(x):
        if not x or x == 0: return 0.0
        return x/100.0 if x > 20 else x

    for raw in blocos:
        try:
            partes = raw.split(";")
            while len(partes) < 8:
                partes.append("0")
            comp, larg, alt, cub, qty, peso, codigo, valor = partes[:8]
            item = {
                "comp": cm_to_m(norm_num(comp)),
                "larg": cm_to_m(norm_num(larg)),
                "alt": cm_to_m(norm_num(alt)),
                "cub": norm_num(cub),
                "qty": int(norm_num(qty)) if norm_num(qty) > 0 else 1,
                "peso": norm_num(peso),
                "codigo": (codigo or "").strip(),
                "valor": norm_num(valor),
            }
            itens.append(item)
        except Exception as e:
            print(f"[WARN] Erro parse item: {raw} - {e}")
            continue
    return itens

# ==========================
# ENDPOINTS
# ==========================
@app.route("/health")
def health():
    return {
        "ok": True,
        "cep_origem": CEP_ORIGEM,
        "valores": DATA["consts"],
        "itens_catalogo": len(DATA["catalogo"]),
        "faixas_configuradas": len(CEP_FAIXAS_KM),
    }

@app.route("/frete")
def frete():
    # Autenticação
    token = request.args.get("token", "")
    if token != TOKEN_SECRETO:
        return Response("Token inválido", status=403, mimetype="text/plain")

    # Parâmetros
    cep_origem_param = request.args.get("cep_origem", CEP_ORIGEM)
    cep_destino = request.args.get("cep_destino", "")
    prods = request.args.get("prods", "")

    if not cep_destino or not prods:
        return Response("Parâmetros insuficientes (cep_destino, prods)", status=400, mimetype="text/plain")

    # Parse produtos
    itens = parse_prods(prods)
    if not itens:
        return Response("Nenhum item válido em 'prods'", status=400, mimetype="text/plain")

    # Constantes base
    valor_km = DATA["consts"].get("VALOR_KM", DEFAULT_VALOR_KM)
    tam_caminhao = DATA["consts"].get("TAM_CAMINHAO", DEFAULT_TAM_CAMINHAO)

    # Permite override via parâmetro (para testes)
    try:
        if request.args.get("valor_km"):
            valor_km = float(str(request.args["valor_km"]).replace(",", "."))
        if request.args.get("tam_caminhao"):
            tam_caminhao = float(str(request.args["tam_caminhao"]).replace(",", "."))
        if request.args.get("km"):
            # opcional: força km direto da query
            km_forcado = float(str(request.args["km"]).replace(",", "."))
        else:
            km_forcado = None
    except:
        km_forcado = None

    # ====== KM POR FAIXA DE CEP ======
    if km_forcado is not None and km_forcado > 0:
        km = km_forcado
        km_fonte = "forcado_parametro"
        faixa_label = "manual"
    else:
        km, faixa_label = km_por_faixa(cep_destino)
        km_fonte = "faixa_cep"

    # ====== CALCULA FRETE POR PRODUTO ======
    total = 0.0
    itens_xml = []
    
    for it in itens:
        nome = it["codigo"] or "Item"
        
        # Busca tamanho no catálogo ou calcula pelas dimensões
        tam_catalogo = DATA["catalogo"].get(nome)
        if tam_catalogo is None:
            tam_catalogo = tamanho_peca_por_nome(nome, it["alt"], it["larg"])
            if tam_catalogo == 0:
                tam_catalogo = max(it["comp"], it["larg"], it["alt"])
        
        # Calcula valor unitário e total
        v_unit = calcula_valor_item(tam_catalogo, km, valor_km, tam_caminhao)
        v_tot = v_unit * max(1, it["qty"])
        total += v_tot
        
        itens_xml.append(f"""
      <item>
        <codigo>{nome}</codigo>
        <quantidade>{it['qty']}</quantidade>
        <diametro_metros>{tam_catalogo:.3f}</diametro_metros>
        <km_distancia>{km:.1f}</km_distancia>
        <valor_unitario>{v_unit:.2f}</valor_unitario>
        <valor_total>{v_tot:.2f}</valor_total>
      </item>""")

    # Monta resposta XML
    debug_info = (f"<debug "
                  f"cep_origem='{cep_origem_param}' "
                  f"cep_destino='{cep_destino}' "
                  f"km='{km:.1f}' "
                  f"fonte_km='{km_fonte}' "
                  f"faixa_label='{faixa_label}' "
                  f"valor_km='{valor_km}' "
                  f"tam_caminhao='{tam_caminhao}' "
                  f"total_itens='{len(itens)}'/>")

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<cotacao>
  <resultado>
    <codigo>BAKOF</codigo>
    <transportadora>Bakof Log</transportadora>
    <servico>Transporte</servico>
    <transporte>TERRESTRE</transporte>
    <valor>{total:.2f}</valor>
    <prazo_min>4</prazo_min>
    <prazo_max>7</prazo_max>
    <entrega_domiciliar>1</entrega_domiciliar>
    <detalhes>{"".join(itens_xml)}
    </detalhes>
    {debug_info}
  </resultado>
</cotacao>"""
    
    return Response(xml, mimetype="application/xml; charset=utf-8")

# ==========================
# ENDPOINT TESTE FAIXA
# ==========================
@app.route("/teste-faixa")
def teste_faixa():
    """
    Endpoint simples para verificar em qual faixa um CEP cai.
    GET /teste-faixa?destino=90020100
    """
    cep_destino = request.args.get("destino", "")
    if not cep_destino:
        return {"erro": "Informe o parâmetro 'destino'"}, 400
    km, label = km_por_faixa(cep_destino)
    return {"cep_destino": cep_destino, "km": km, "faixa": label}, 200

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    print(f"🚀 Iniciando API de Frete por FAIXAS de CEP")
    print(f"📍 CEP Origem: {CEP_ORIGEM}")
    print(f"🔑 Token: {TOKEN_SECRETO}")
    print(f"📊 Produtos no catálogo: {len(DATA['catalogo'])}")
    print(f"🧭 Faixas configuradas: {len(CEP_FAIXAS_KM)}")
    app.run(host="0.0.0.0", port=port, debug=True)
