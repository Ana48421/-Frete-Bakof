# app.py — API de Frete (Campo Grande/MS) — v4.2 Tray-hardening
import os, math, re
from typing import Dict, Any, List, Tuple, Optional
import pandas as pd
from flask import Flask, request, Response, jsonify

# ==========================
# CONFIG
# ==========================
TOKEN_SECRETO        = os.getenv("TOKEN_SECRETO", "teste123")
CEP_ORIGEM           = os.getenv("CEP_ORIGEM", "79108630")  # Campo Grande/MS
ARQ_PLANILHA         = os.getenv("PLANILHA_FRETE", "tabela de frete atualizada(2)(Recuperado Automaticamente).xlsx")

DEFAULT_VALOR_KM     = float(os.getenv("DEFAULT_VALOR_KM", "7.0"))
DEFAULT_TAM_CAMINHAO = float(os.getenv("DEFAULT_TAM_CAMINHAO", "8.5"))
DEFAULT_KM           = float(os.getenv("DEFAULT_KM", "1500.0"))
DEFAULT_VALOR_FRETE  = float(os.getenv("DEFAULT_VALOR_FRETE", "800.0"))

# quando prods não vier, usar valor fixo? (True) ou estimar ocupação mínima? (False)
FALLBACK_VALOR_FIXO_SEM_PRODUTOS = os.getenv("FALLBACK_VALOR_FIXO_SEM_PRODUTOS", "true").lower() == "true"
OCUPACAO_MINIMA_SEM_PRODUTOS     = float(os.getenv("OCUPACAO_MINIMA_SEM_PRODUTOS", "0.15"))  # fração do caminhão

PALAVRAS_IGNORAR = {
    "VALOR KM","TAMANHO CAMINHAO","TAMANHO CAMINHÃO",
    "CALCULO DE FRETE POR TAMANHO DE PEÇA","CÁLCULO DE FRETE POR TAMANHO DE PEÇA"
}

app = Flask(__name__)

# ==========================
# FAIXAS CEP (resumido: igual ao seu v4.1)
# ==========================
FAIXAS_CEP_KM = [
    ("79108000","79108999",10), ("79000000","79099999",20), ("79100000","79199999",30),
    ("79200000","79999999",100),
    ("78000000","78099999",700), ("78100000","78899999",800),
    ("74000000","76799999",900), ("70000000","73699999",1100), ("77000000","77999999",1400),
    ("87000000","87199999",500), ("86000000","86199999",600), ("85800000","85899999",700),
    ("84000000","84999999",800), ("80000000","82999999",900), ("83000000","83999999",850),
    ("85850000","85869999",1000), ("83400000","83699999",950),
    ("19000000","19999999",800), ("18000000","18999999",900), ("17000000","17999999",1000),
    ("16000000","16999999",1100), ("15000000","15999999",1150), ("14000000","14999999",1200),
    ("13000000","13999999",1300), ("12000000","12999999",1400), ("09000000","09999999",1450),
    ("01000000","08999999",1450), ("11000000","11999999",1500),
    ("89800000","89899999",700), ("89500000","89699999",800), ("89100000","89299999",1000),
    ("89000000","89099999",1100), ("88000000","88099999",1150), ("88300000","88499999",1200),
    ("88700000","88899999",1250),
    ("98000000","98999999",1300), ("99000000","99099999",1400), ("95000000","95999999",1500),
    ("97000000","97999999",1450), ("93000000","93999999",1600), ("92000000","92999999",1650),
    ("94000000","94999999",1700), ("90000000","91999999",1700), ("96000000","96999999",1800),
    ("38000000","38999999",1400), ("39000000","39999999",1350), ("37000000","37999999",1500),
    ("35000000","35999999",1600), ("36000000","36999999",1650), ("32000000","34999999",1700),
    ("30000000","31999999",1750),
    ("28000000","28999999",1700), ("27000000","27999999",1750), ("25000000","26999999",1800),
    ("24000000","24999999",1850), ("20000000","23999999",1900),
    ("29000000","29999999",2000),
    ("40000000","42999999",2200), ("43000000","48999999",2100), ("49000000","49999999",2400),
    ("57000000","57999999",2500), ("50000000","56999999",2600), ("58000000","58999999",2700),
    ("59000000","59999999",2800), ("60000000","63999999",2900), ("64000000","64999999",2850),
    ("65000000","65999999",3000),
    ("69300000","69399999",2200), ("69900000","69999999",2400), ("76800000","76999999",2000),
    ("69000000","69899999",2600), ("66000000","68899999",2800), ("68900000","68999999",3200),
]

# ==========================
# HELPERS
# ==========================
def limpar_cep(cep: str) -> str:
    s = re.sub(r'\D','', str(cep or ""))
    return s[:8].zfill(8) if s else "00000000"

def xml_response(xml_str: str) -> Response:
    resp = Response(xml_str, status=200)
    resp.headers["Content-Type"] = "text/xml; charset=utf-8"
    resp.headers["Cache-Control"] = "no-store"
    return resp

def get_json_safe() -> Dict[str, Any]:
    try:
        if request.is_json:
            data = request.get_json(silent=True) or {}
            return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}

def get_param(*keys: str, default: Optional[str] = "") -> str:
    data_json = get_json_safe()
    for k in keys:
        if k in request.args and str(request.args.get(k)).strip():
            return str(request.args.get(k)).strip()
        if k in request.form and str(request.form.get(k)).strip():
            return str(request.form.get(k)).strip()
        if k in data_json and str(data_json.get(k)).strip():
            return str(data_json.get(k)).strip()
    return default or ""

def buscar_km_por_cep(cep_destino: str) -> Tuple[float, str]:
    cep = limpar_cep(cep_destino)
    try:
        n = int(cep)
        for a,b,km in FAIXAS_CEP_KM:
            if int(a) <= n <= int(b):
                return float(km), "faixa_cep"
    except Exception:
        pass
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
        return float(km_uf.get(uf, DEFAULT_KM)), f"uf_{uf}"
    return DEFAULT_KM, "cep_nao_encontrado"

def uf_por_cep(cep8: str) -> Optional[str]:
    UF_RANGES = [
        ("SP","01000000","19999999"), ("RJ","20000000","28999999"), ("ES","29000000","29999999"),
        ("MG","30000000","39999999"), ("BA","40000000","48999999"), ("SE","49000000","49999999"),
        ("PE","50000000","56999999"), ("AL","57000000","57999999"), ("PB","58000000","58999999"),
        ("RN","59000000","59999999"), ("CE","60000000","63999999"), ("PI","64000000","64999999"),
        ("MA","65000000","65999999"), ("PA","66000000","68899999"), ("AP","68900000","68999999"),
        ("AM","69000000","69899999"), ("RR","69300000","69399999"), ("AC","69900000","69999999"),
        ("DF","70000000","73699999"), ("GO","72800000","76799999"), ("TO","77000000","77999999"),
        ("MT","78000000","78899999"), ("MS","79000000","79999999"), ("PR","80000000","87999999"),
        ("SC","88000000","89999999"), ("RS","90000000","99999999"),
    ]
    try:
        n = int(cep8)
    except Exception:
        return None
    for uf,a,b in UF_RANGES:
        if int(a) <= n <= int(b):
            return uf
    return None

# ==========================
# PLANILHA (igual ao seu, robusto a ausência)
# ==========================
def limpar_texto(x: Any) -> str:
    if not isinstance(x, str): return ""
    return " ".join(x.replace("\n"," ").split()).strip()

def extrai_numero_linha(row) -> Optional[float]:
    for v in row:
        if v is None or pd.isna(v): continue
        s = str(v).strip().upper()
        if s in ("","NAN","NONE","NULL"): continue
        s = s.replace(",", ".")
        s = re.sub(r'(METROS?|KM|R\$|REAIS|/KM)', '', s, flags=re.IGNORECASE).strip()
        try:
            f = float(s)
            if math.isfinite(f) and f>0: return f
        except Exception:
            pass
    return None

def carregar_constantes(xls: pd.ExcelFile) -> Dict[str, float]:
    valor_km, tam_cam = DEFAULT_VALOR_KM, DEFAULT_TAM_CAMINHAO
    for aba in ("BASE_CALCULO","D","BASE","CONSTANTES"):
        if aba not in xls.sheet_names: continue
        try:
            raw = pd.read_excel(xls, aba, header=None)
            for _,row in raw.iterrows():
                texto = " ".join([str(v).upper() for v in row if isinstance(v,str)])
                if "VALOR" in texto or "KM" in texto:
                    n = extrai_numero_linha(row)
                    if n and 3<=n<=50: valor_km = n
                if "TAMANHO" in texto and "CAMINH" in texto:
                    n = extrai_numero_linha(row)
                    if n and 3<=n<=20:  tam_cam = n
        except Exception:
            pass
    return {"VALOR_KM": valor_km, "TAM_CAMINHAO": tam_cam}

def carregar_cadastro_produtos(xls: pd.ExcelFile) -> pd.DataFrame:
    for aba in ("CADASTRO_PRODUTO","CADASTRO","PRODUTOS"):
        if aba not in xls.sheet_names: continue
        try:
            raw = pd.read_excel(xls, aba, header=None)
            nc = raw.shape[1]
            nome_col = 2 if nc>2 else 0
            dim1_col = 3 if nc>3 else (1 if nc>1 else 0)
            dim2_col = 4 if nc>4 else (2 if nc>2 else 1)
            df = raw[[nome_col, dim1_col, dim2_col]].copy()
            df.columns = ["nome","dim1","dim2"]
            df["nome"] = df["nome"].apply(limpar_texto)
            df = df[~df["nome"].str.upper().isin(PALAVRAS_IGNORAR)]
            df = df[df["nome"].astype(str).str.len()>0]
            df["dim1"] = pd.to_numeric(df["dim1"], errors="coerce").fillna(0.0)
            df["dim2"] = pd.to_numeric(df["dim2"], errors="coerce").fillna(0.0)
            df = df.drop_duplicates(subset=["nome"], keep="first").reset_index(drop=True)
            return df[["nome","dim1","dim2"]]
        except Exception:
            pass
    return pd.DataFrame(columns=["nome","dim1","dim2"])

def tipo_produto(nome: str) -> str:
    n = (nome or "").lower()
    if "fossa" in n: return "fossa"
    if "vertical" in n: return "vertical"
    if "horizontal" in n: return "horizontal"
    if "tc" in n and ("10.000" in n or "10000" in n or "10.0" in n): return "tc_ate_10k"
    return "auto"

def tamanho_peca_por_nome(nome: str, d1: float, d2: float) -> float:
    t = tipo_produto(nome)
    if t in ("fossa","vertical"):         return float(d1 or 0.0)
    if t in ("horizontal","tc_ate_10k"):  return float(d2 or 0.0)
    return float(max(float(d1 or 0.0), float(d2 or 0.0)))

def montar_catalogo_tamanho(df: pd.DataFrame) -> Dict[str, float]:
    mapa = {}
    for _,r in df.iterrows():
        try:
            nome = limpar_texto(r["nome"])
            if not nome or nome.upper() in PALAVRAS_IGNORAR: continue
            tam = tamanho_peca_por_nome(nome, float(r["dim1"]), float(r["dim2"]))
            if tam>0: mapa[nome] = tam
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
        return {"consts": {"VALOR_KM": DEFAULT_VALOR_KM, "TAM_CAMINHAO": DEFAULT_TAM_CAMINHAO}, "catalogo": {}}

DATA = carregar_tudo()

# ==========================
# CÁLCULO
# ==========================
def calcula_valor_item(tamanho_peca_m: float, km: float, valor_km: float, tam_caminhao: float) -> float:
    if tamanho_peca_m <= 0 or tam_caminhao <= 0: return 0.0
    ocup = float(tamanho_peca_m) / float(tam_caminhao)
    return round(float(valor_km) * float(km) * ocup, 2)

def parse_prods(s: str) -> List[Dict[str, Any]]:
    itens: List[Dict[str, Any]] = []
    if not s: return itens
    blocos: List[str] = []
    for sep in ("/","|"):
        if sep in s:
            blocos = [b for b in s.split(sep) if b.strip()]
            break
    if not blocos: blocos = [s]

    def norm(x):
        if x is None: return 0.0
        z = str(x).strip().lower()
        if z in ("","null","none","nan"): return 0.0
        z = z.replace(",", ".")
        try: return float(z)
        except: return 0.0

    def cm_to_m(x):
        if not x or x == 0: return 0.0
        return x/100.0 if x>20 else x

    for raw in blocos:
        try:
            p = raw.split(";")
            if len(p) < 8:
                print(f"[WARN] Item com menos de 8 campos: {raw}")
                continue
            comp, larg, alt, cub, qty, peso, codigo, valor = p[:8]
            comp_m = cm_to_m(norm(comp)); larg_m = cm_to_m(norm(larg)); alt_m = cm_to_m(norm(alt))
            itens.append({
                "comp": comp_m, "larg": larg_m, "alt": alt_m,
                "cub": norm(cub), "qty": int(norm(qty)) if norm(qty)>0 else 1,
                "peso": norm(peso), "codigo": (codigo or "").strip(), "valor": norm(valor)
            })
        except Exception as e:
            print(f"[ERROR] Erro parse item: {raw} - {e}")
    return itens

# ==========================
# XML BUILDERS
# ==========================
def xml_cotacao(valor: float, km: float, uf: Optional[str], fonte: str, itens_xml: str, prazo_min=4, prazo_max=7, prazo=None, info_extra:str="") -> str:
    if prazo is None:
        prazo = max(prazo_min, (prazo_min + prazo_max)//2)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<cotacao>
  <resultado>
    <codigo>BAKOF</codigo>
    <transportadora>Bakof Logistica</transportadora>
    <transporte>TERRESTRE</transporte>
    <valor>{valor:.2f}</valor>
    <prazo>{int(prazo)}</prazo>
    <prazo_min>{int(prazo_min)}</prazo_min>
    <prazo_max>{int(prazo_max)}</prazo_max>
    <entrega_domiciliar>1</entrega_domiciliar>
    <detalhes>
      <origem>Campo Grande/MS</origem>
      <km>{km:.1f}</km>
      <uf>{uf or 'N/A'}</uf>
      <fonte_km>{fonte}</fonte_km>
      {info_extra}
      <itens>{itens_xml}</itens>
    </detalhes>
  </resultado>
</cotacao>"""

def xml_erro(mensagem: str, cep:str="", info_extra:str="") -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<cotacao>
  <resultado>
    <codigo>BAKOF</codigo>
    <transportadora>Bakof Logistica</transportadora>
    <transporte>TERRESTRE</transporte>
    <valor>{DEFAULT_VALOR_FRETE:.2f}</valor>
    <prazo>10</prazo>
    <prazo_min>7</prazo_min>
    <prazo_max>15</prazo_max>
    <entrega_domiciliar>1</entrega_domiciliar>
    <erro>{mensagem}</erro>
    <detalhes>
      <origem>Campo Grande/MS</origem>
      <cep_consultado>{limpar_cep(cep)}</cep_consultado>
      {info_extra}
    </detalhes>
  </resultado>
</cotacao>"""

# ==========================
# ENDPOINTS
# ==========================
@app.route("/", methods=["GET","POST"])
def index():
    # Se vier parâmetros típicos da Tray, já calcula
    data = get_json_safe()
    if any(k in request.args or k in request.form or k in data for k in ("cep","cep_destino","cepDestino","prods","produtos","products")):
        return frete()
    return jsonify({
        "api":"Bakof Frete",
        "versao":"4.2 - Campo Grande/MS",
        "cep_origem": CEP_ORIGEM,
        "faixas_cadastradas": len(FAIXAS_CEP_KM),
        "endpoints": {"/health":"status","/frete":"calcular frete","/frete/tray-debug":"echo de parâmetros recebidos"}
    })

@app.route("/health")
def health():
    return jsonify({
        "ok": True,
        "consts": DATA["consts"],
        "catalogo_produtos": len(DATA["catalogo"]),
        "faixas_cep": len(FAIXAS_CEP_KM),
        "defaults": {"km": DEFAULT_KM, "valor_fixo": DEFAULT_VALOR_FRETE}
    })

@app.route("/frete/tray-debug", methods=["GET","POST"])
def tray_debug():
    return jsonify({
        "args": request.args.to_dict(),
        "form": request.form.to_dict(),
        "json": get_json_safe(),
        "headers": {k:v for k,v in request.headers.items()}
    })

@app.route("/frete", methods=["GET","POST"])
def frete():
    # token (opcional)
    token = get_param("token", default="")
    if token and token != TOKEN_SECRETO:
        return xml_response(xml_erro("Token inválido"))

    cep_destino = get_param("cep_destino","cepDestino","cep", default="")
    prods_raw   = get_param("prods","produtos","products", default="")

    print(f"[DEBUG] CEP Destino: {cep_destino}")
    print(f"[DEBUG] Produtos: {prods_raw}")

    if not cep_destino:
        return xml_response(xml_erro("Parâmetro 'cep_destino' (ou 'cep') ausente"))

    # Busca KM
    km, fonte = buscar_km_por_cep(cep_destino)
    uf = uf_por_cep(limpar_cep(cep_destino))

    # Quando não vierem produtos, evitar sumiço na Tray: responde com fallback
    if not prods_raw:
        if FALLBACK_VALOR_FIXO_SEM_PRODUTOS:
            xml = xml_cotacao(DEFAULT_VALOR_FRETE, km, uf, fonte, itens_xml="", prazo_min=5, prazo_max=10,
                              info_extra="<observacao>Sem produtos no payload - valor fixo aplicado</observacao>")
            return xml_response(xml)
        else:
            valor_km = DATA["consts"].get("VALOR_KM", DEFAULT_VALOR_KM)
            tam_cam  = DATA["consts"].get("TAM_CAMINHAO", DEFAULT_TAM_CAMINHAO)
            v = round(valor_km * km * OCUPACAO_MINIMA_SEM_PRODUTOS, 2)
            xml = xml_cotacao(v, km, uf, fonte, itens_xml="", prazo_min=5, prazo_max=10,
                              info_extra=f"<ocupacao_minima>{OCUPACAO_MINIMA_SEM_PRODUTOS:.2f}</ocupacao_minima>")
            return xml_response(xml)

    itens = parse_prods(prods_raw)
    print(f"[DEBUG] Itens parseados: {len(itens)}")
    if not itens:
        # ainda assim responder algo para a Tray exibir
        xml = xml_cotacao(DEFAULT_VALOR_FRETE, km, uf, fonte, itens_xml="",
                          info_extra="<observacao>Produtos inválidos - valor fixo</observacao>")
        return xml_response(xml)

    valor_km = DATA["consts"].get("VALOR_KM", DEFAULT_VALOR_KM)
    tam_cam  = DATA["consts"].get("TAM_CAMINHAO", DEFAULT_TAM_CAMINHAO)

    # overrides opcionais
    try:
        v_override = get_param("valor_km","vl_km", default="")
        if v_override: valor_km = float(str(v_override).replace(",", "."))
        t_override = get_param("tam_caminhao","tamanho_caminhao", default="")
        if t_override: tam_cam = float(str(t_override).replace(",", "."))
    except Exception:
        pass

    total = 0.0
    itens_xml = []
    for it in itens:
        nome = it["codigo"] or "Item"
        tam_catalogo = DATA["catalogo"].get(nome)
        if tam_catalogo is None:
            tam_catalogo = max(it["comp"], it["larg"], it["alt"]) or 2.0
        v_unit = calcula_valor_item(tam_catalogo, km, valor_km, tam_cam)
        v_tot  = v_unit * max(1, it["qty"])
        total += v_tot
        itens_xml.append(f"""
      <item>
        <codigo>{nome}</codigo>
        <quantidade>{it['qty']}</quantidade>
        <tamanho_metros>{tam_catalogo:.3f}</tamanho_metros>
        <valor_unitario>{v_unit:.2f}</valor_unitario>
        <valor_total>{v_tot:.2f}</valor_total>
      </item>""")

    xml = xml_cotacao(round(total,2), km, uf, fonte, "".join(itens_xml))
    return xml_response(xml)

if __name__ == "__main__":
    port = int(os.getenv("PORT","8000"))
    print("="*70)
    print("🚀 API de Frete Bakof - Campo Grande/MS (Tray-hardening v4.2)")
    print("="*70)
    print(f"📮 CEP Origem: {CEP_ORIGEM}")
    print(f"🔑 Token: {TOKEN_SECRETO}")
    print(f"📦 Faixas CEP: {len(FAIXAS_CEP_KM)}")
    print(f"💰 Valor/KM: R$ {DATA['consts']['VALOR_KM']:.2f}")
    print(f"🚛 Tamanho caminhão: {DATA['consts']['TAM_CAMINHAO']:.1f} m")
    print(f"📍 KM padrão (CEP não encontrado): {DEFAULT_KM} km")
    print(f"💵 Valor fixo fallback: R$ {DEFAULT_VALOR_FRETE:.2f}")
    print(f"🌐 http://0.0.0.0:{port}")
    print("="*70)
    app.run(host="0.0.0.0", port=port, debug=False)
