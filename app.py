# app.py — API de Frete com FAIXAS DE CEP (partindo de Campo Grande/MS) — v4.1 (compat Tray)
import os
import math
import re
from typing import Dict, Any, List, Tuple, Optional
import pandas as pd
from flask import Flask, request, Response, jsonify

# ==========================
# CONFIGURAÇÕES
# ==========================
TOKEN_SECRETO = os.getenv("TOKEN_SECRETO", "teste123")
CEP_ORIGEM = os.getenv("CEP_ORIGEM", "79108630")  # Campo Grande/MS - CD Principal
ARQ_PLANILHA = os.getenv("PLANILHA_FRETE", "tabela de frete atualizada(2)(Recuperado Automaticamente).xlsx")

DEFAULT_VALOR_KM = float(os.getenv("DEFAULT_VALOR_KM", "7.0"))
DEFAULT_TAM_CAMINHAO = float(os.getenv("DEFAULT_TAM_CAMINHAO", "8.5"))
DEFAULT_KM = float(os.getenv("DEFAULT_KM", "1500.0"))  # KM padrão p/ CEPs não encontrados
DEFAULT_VALOR_FRETE = float(os.getenv("DEFAULT_VALOR_FRETE", "800.0"))  # Valor fixo p/ CEPs não encontrados

PALAVRAS_IGNORAR = {
    "VALOR KM", "TAMANHO CAMINHAO", "TAMANHO CAMINHÃO",
    "CALCULO DE FRETE POR TAMANHO DE PEÇA", "CÁLCULO DE FRETE POR TAMANHO DE PEÇA"
}

app = Flask(__name__)

# ==========================
# FAIXAS DE CEP -> KM (ORIGEM: CAMPO GRANDE/MS 79108630)
# IMPORTANTE: Faixas mais específicas devem vir PRIMEIRO
# ==========================
FAIXAS_CEP_KM = [
    ("79108000", "79108999", 10),    # Campo Grande - CD LOCAL
    ("79000000", "79099999", 20),    # Campo Grande região central
    ("79100000", "79199999", 30),    # Campo Grande região expandida
    ("79200000", "79999999", 100),   # Interior de MS

    # MT
    ("78000000", "78099999", 700),
    ("78100000", "78899999", 800),

    # GO / DF / TO
    ("74000000", "76799999", 900),
    ("70000000", "73699999", 1100),
    ("77000000", "77999999", 1400),

    # PR
    ("87000000", "87199999", 500),
    ("86000000", "86199999", 600),
    ("85800000", "85899999", 700),
    ("84000000", "84999999", 800),
    ("80000000", "82999999", 900),
    ("83000000", "83999999", 850),
    ("85850000", "85869999", 1000),
    ("83400000", "83699999", 950),

    # SP
    ("19000000", "19999999", 800),
    ("18000000", "18999999", 900),
    ("17000000", "17999999", 1000),
    ("16000000", "16999999", 1100),
    ("15000000", "15999999", 1150),
    ("14000000", "14999999", 1200),
    ("13000000", "13999999", 1300),
    ("12000000", "12999999", 1400),
    ("09000000", "09999999", 1450),
    ("01000000", "08999999", 1450),
    ("11000000", "11999999", 1500),

    # SC
    ("89800000", "89899999", 700),
    ("89500000", "89699999", 800),
    ("89100000", "89299999", 1000),
    ("89000000", "89099999", 1100),
    ("88000000", "88099999", 1150),
    ("88300000", "88499999", 1200),
    ("88700000", "88899999", 1250),

    # RS
    ("98000000", "98999999", 1300),
    ("99000000", "99099999", 1400),
    ("95000000", "95999999", 1500),
    ("97000000", "97999999", 1450),
    ("93000000", "93999999", 1600),
    ("92000000", "92999999", 1650),
    ("94000000", "94999999", 1700),
    ("90000000", "91999999", 1700),
    ("96000000", "96999999", 1800),

    # MG
    ("38000000", "38999999", 1400),
    ("39000000", "39999999", 1350),
    ("37000000", "37999999", 1500),
    ("35000000", "35999999", 1600),
    ("36000000", "36999999", 1650),
    ("32000000", "34999999", 1700),
    ("30000000", "31999999", 1750),

    # RJ
    ("28000000", "28999999", 1700),
    ("27000000", "27999999", 1750),
    ("25000000", "26999999", 1800),
    ("24000000", "24999999", 1850),
    ("20000000", "23999999", 1900),

    # ES
    ("29000000", "29999999", 2000),

    # BA + Nordeste
    ("40000000", "42999999", 2200),
    ("43000000", "48999999", 2100),
    ("49000000", "49999999", 2400),
    ("57000000", "57999999", 2500),
    ("50000000", "56999999", 2600),
    ("58000000", "58999999", 2700),
    ("59000000", "59999999", 2800),
    ("60000000", "63999999", 2900),
    ("64000000", "64999999", 2850),
    ("65000000", "65999999", 3000),

    # Norte
    ("69300000", "69399999", 2200),
    ("69900000", "69999999", 2400),
    ("76800000", "76999999", 2000),
    ("69000000", "69899999", 2600),
    ("66000000", "68899999", 2800),
    ("68900000", "68999999", 3200),
]

# ==========================
# HELPERS
# ==========================
def limpar_cep(cep: str) -> str:
    s = re.sub(r'\D', '', str(cep or ""))
    return s[:8].zfill(8) if s else "00000000"

def get_json_safe() -> Dict[str, Any]:
    try:
        if request.is_json:
            data = request.get_json(silent=True) or {}
            return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}

def get_param(*keys: str, default: Optional[str] = "") -> str:
    """
    Busca parâmetros em ordem:
    - querystring (request.args)
    - form-urlencoded (request.form)
    - JSON body (request.get_json)
    Suporta múltiplos aliases: get_param("cep_destino","cep","cepDestino")
    """
    data_json = get_json_safe()
    for k in keys:
        # args
        if k in request.args and str(request.args.get(k)).strip():
            return str(request.args.get(k)).strip()
        # form
        if k in request.form and str(request.form.get(k)).strip():
            return str(request.form.get(k)).strip()
        # json
        if k in data_json and str(data_json.get(k)).strip():
            return str(data_json.get(k)).strip()
    return default or ""

def buscar_km_por_cep(cep_destino: str) -> Tuple[float, str]:
    cep = limpar_cep(cep_destino)
    # tenta faixa
    try:
        cep_num = int(cep)
        for ini, fim, km in FAIXAS_CEP_KM:
            if int(ini) <= cep_num <= int(fim):
                return (float(km), "faixa_cep")
    except Exception:
        pass

    # fallback por UF
    uf = uf_por_cep(cep)
    if uf:
        km_uf = {
            "MS": 50, "MT": 700, "GO": 900, "DF": 1100, "TO": 1400,
            "PR": 700, "SP": 1100, "SC": 1000, "RS": 1500,
            "MG": 1600, "RJ": 1800, "ES": 2000, "BA": 2200,
            "SE": 2400, "AL": 2500, "PE": 2600, "PB": 2700,
            "RN": 2800, "CE": 2900, "PI": 2850, "MA": 3000,
            "RR": 2200, "AC": 2400, "RO": 2000, "AM": 2600,
            "PA": 2800, "AP": 3200,
        }
        return (float(km_uf.get(uf, DEFAULT_KM)), f"uf_{uf}")

    print(f"[WARN] CEP não encontrado: {cep} - usando valor padrão")
    return (DEFAULT_KM, "cep_nao_encontrado")

def uf_por_cep(cep8: str) -> Optional[str]:
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
    except Exception:
        return None
    for uf, a, b in UF_CEP_RANGES:
        if int(a) <= n <= int(b):
            return uf
    return None

# ==========================
# PLANILHA
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
        except Exception:
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
        except Exception:
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
        except Exception:
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
        except Exception:
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
# CÁLCULO
# ==========================
def calcula_valor_item(tamanho_peca_m: float, km: float, valor_km: float, tam_caminhao: float) -> float:
    if tamanho_peca_m <= 0 or tam_caminhao <= 0:
        return 0.0
    ocupacao = float(tamanho_peca_m) / float(tam_caminhao)
    return round(float(valor_km) * float(km) * ocupacao, 2)

def parse_prods(prods_str: str) -> List[Dict[str, Any]]:
    itens = []
    if not prods_str:
        return itens

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
        except Exception:
            return 0.0

    def cm_to_m(x):
        if not x or x == 0:
            return 0.0
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
    # Se a Tray chamar a raiz com parâmetros, calcular frete
    if any(k in request.args or k in request.form for k in ("cep", "cep_destino", "cepDestino", "prods", "produtos", "products")):
        return frete()
    data = get_json_safe()
    if any(k in data for k in ("cep", "cep_destino", "cepDestino", "prods", "produtos", "products")):
        return frete()

    return jsonify({
        "api": "Bakof Frete",
        "versao": "4.1 - CD Campo Grande/MS",
        "cd_origem": "Campo Grande/MS",
        "cep_origem": CEP_ORIGEM,
        "faixas_cadastradas": len(FAIXAS_CEP_KM),
        "endpoints": {
            "/health": "Status da API",
            "/frete": "Calcular frete",
            "/consultar-cep": "Consultar KM de um CEP"
        }
    })

@app.route("/health")
def health():
    return jsonify({
        "ok": True,
        "cd_origem": "Campo Grande/MS",
        "cep_origem": CEP_ORIGEM,
        "valores": DATA["consts"],
        "produtos_catalogo": len(DATA["catalogo"]),
        "faixas_cep": len(FAIXAS_CEP_KM),
        "default_km": DEFAULT_KM,
        "default_valor_frete": DEFAULT_VALOR_FRETE,
    })

@app.route("/consultar-cep")
def consultar_cep():
    cep = get_param("cep", "cep_destino", "cepDestino", default="")
    if not cep:
        return jsonify({"erro": "Informe o parâmetro 'cep'"}), 400
    km, fonte = buscar_km_por_cep(cep)
    uf = uf_por_cep(limpar_cep(cep))
    return jsonify({
        "cep": limpar_cep(cep),
        "uf": uf,
        "km": km,
        "fonte": fonte,
        "origem": "Campo Grande/MS",
        "valor_fixo_se_nao_encontrado": DEFAULT_VALOR_FRETE if fonte == "cep_nao_encontrado" else None
    })

@app.route("/frete", methods=["GET", "POST"])
def frete():
    # Autenticação (opcional para Tray)
    token = get_param("token", default="")
    if token and token != TOKEN_SECRETO:
        return Response("Token inválido", status=403)

    # Parâmetros com aliases comuns da Tray
    cep_destino = get_param("cep_destino", "cepDestino", "cep", default="")
    prods = get_param("prods", "produtos", "products", default="")

    print(f"[DEBUG] CEP Destino: {cep_destino}")
    print(f"[DEBUG] Produtos(raw): {prods}")

    if not cep_destino:
        return Response("Parâmetro 'cep_destino' (ou 'cep') obrigatório", status=400)
    if not prods:
        return Response("Parâmetro 'prods' (ou 'produtos') obrigatório", status=400)

    itens = parse_prods(prods)
    print(f"[DEBUG] Itens parseados: {len(itens)}")
    if not itens:
        return Response("Nenhum item válido em 'prods'", status=400)

    # Constantes
    valor_km = DATA["consts"].get("VALOR_KM", DEFAULT_VALOR_KM)
    tam_caminhao = DATA["consts"].get("TAM_CAMINHAO", DEFAULT_TAM_CAMINHAO)

    # Overrides via parâmetros (em qualquer meio)
    try:
        v_override = get_param("valor_km", "vl_km", default="")
        if v_override:
            valor_km = float(str(v_override).replace(",", "."))
        t_override = get_param("tam_caminhao", "tamanho_caminhao", default="")
        if t_override:
            tam_caminhao = float(str(t_override).replace(",", "."))
    except Exception:
        pass

    km, km_fonte = buscar_km_por_cep(cep_destino)
    print(f"[DEBUG] KM calculado: {km} ({km_fonte})")

    usar_valor_fixo = (km_fonte == "cep_nao_encontrado")

    if usar_valor_fixo:
        total = round(float(DEFAULT_VALOR_FRETE), 2)
        uf = uf_por_cep(limpar_cep(cep_destino))
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<cotacao>
  <resultado>
    <codigo>BAKOF</codigo>
    <transportadora>Bakof Logistica</transportadora>
    <transporte>TERRESTRE</transporte>
    <valor>{total:.2f}</valor>
    <prazo>10</prazo>
    <prazo_min>7</prazo_min>
    <prazo_max>15</prazo_max>
    <entrega_domiciliar>1</entrega_domiciliar>
    <detalhes>
      <origem>Campo Grande/MS</origem>
      <km>{km:.1f}</km>
      <uf>{uf or 'N/A'}</uf>
      <fonte_km>{km_fonte}</fonte_km>
      <valor_fixo>true</valor_fixo>
      <observacao>CEP não encontrado - valor estimado</observacao>
    </detalhes>
  </resultado>
</cotacao>"""
        return Response(xml, mimetype="text/xml; charset=utf-8")

    # Fluxo normal
    total = 0.0
    itens_xml = []

    for it in itens:
        nome = it["codigo"] or "Item"
        tam_catalogo = DATA["catalogo"].get(nome)
        if tam_catalogo is None:
            tam_catalogo = max(it["comp"], it["larg"], it["alt"]) or 2.0
        v_unit = calcula_valor_item(tam_catalogo, km, valor_km, tam_caminhao)
        v_tot = v_unit * max(1, it["qty"])
        total += v_tot
        itens_xml.append(f"""
      <item>
        <codigo>{nome}</codigo>
        <quantidade>{it['qty']}</quantidade>
        <tamanho_metros>{tam_catalogo:.3f}</tamanho_metros>
        <valor_unitario>{v_unit:.2f}</valor_unitario>
        <valor_total>{v_tot:.2f}</valor_total>
      </item>""")

    uf = uf_por_cep(limpar_cep(cep_destino))
    total = round(total, 2)

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<cotacao>
  <resultado>
    <codigo>BAKOF</codigo>
    <transportadora>Bakof Logistica</transportadora>
    <transporte>TERRESTRE</transporte>
    <valor>{total:.2f}</valor>
    <prazo>6</prazo>
    <prazo_min>4</prazo_min>
    <prazo_max>7</prazo_max>
    <entrega_domiciliar>1</entrega_domiciliar>
    <detalhes>
      <origem>Campo Grande/MS</origem>
      <km>{km:.1f}</km>
      <uf>{uf or 'N/A'}</uf>
      <fonte_km>{km_fonte}</fonte_km>
      <valor_km>{valor_km:.2f}</valor_km>
      <itens>{"".join(itens_xml)}
      </itens>
    </detalhes>
  </resultado>
</cotacao>"""

    # A Tray costuma exigir text/xml
    return Response(xml, mimetype="text/xml; charset=utf-8")

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    print("=" * 70)
    print("🚀 API de Frete Bakof - CD Campo Grande/MS (Tray compat)")
    print("=" * 70)
    print(f"📍 CD Origem: Campo Grande/MS")
    print(f"📮 CEP Origem: {CEP_ORIGEM}")
    print(f"🔑 Token: {TOKEN_SECRETO}")
    print(f"📊 Produtos: {len(DATA['catalogo'])}")
    print(f"📦 Faixas CEP: {len(FAIXAS_CEP_KM)}")
    print(f"💰 Valor/KM: R$ {DATA['consts']['VALOR_KM']:.2f}")
    print(f"🚛 Tamanho caminhão: {DATA['consts']['TAM_CAMINHAO']:.1f}m")
    print(f"📍 KM padrão (CEP não encontrado): {DEFAULT_KM}km")
    print(f"💵 Valor fixo (CEP não encontrado): R$ {DEFAULT_VALOR_FRETE:.2f}")
    print(f"🌐 Servidor: http://0.0.0.0:{port}")
    print("=" * 70)
    app.run(host="0.0.0.0", port=port, debug=False)
