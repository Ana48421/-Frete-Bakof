# app.py — FRETE por Município (prioridade) + Faixa CEP + UF — v4.3 Tray-hardening (CD em MS)
import os, math, re
from typing import Dict, Any, List, Tuple, Optional
import pandas as pd
from flask import Flask, request, Response, jsonify

# ==========================
# CONFIG
# ==========================
TOKEN_SECRETO = os.getenv("TOKEN_SECRETO", "teste123")
ARQ_PLANILHA  = os.getenv("PLANILHA_FRETE", "tabela de frete atualizada(2)(Recuperado Automaticamente).xlsx")

# CD de origem em MS
CD_ORIGEM  = os.getenv("CD_ORIGEM", "Campo Grande/MS")
CEP_ORIGEM = os.getenv("CEP_ORIGEM", "79108630")

# Nome da transportadora (exibido no XML)
TRANSPORTADORA_NOME = os.getenv("TRANSPORTADORA_NOME", "Ms")

DEFAULT_VALOR_KM     = float(os.getenv("DEFAULT_VALOR_KM", "7.0"))
DEFAULT_TAM_CAMINHAO = float(os.getenv("DEFAULT_TAM_CAMINHAO", "8.5"))
DEFAULT_KM           = float(os.getenv("DEFAULT_KM", "450.0"))
DEFAULT_VALOR_FRETE  = float(os.getenv("DEFAULT_VALOR_FRETE", "800.0"))

# Quando não vierem produtos no payload:
FALLBACK_VALOR_FIXO_SEM_PRODUTOS = os.getenv("FALLBACK_VALOR_FIXO_SEM_PRODUTOS", "true").lower() == "true"
OCUPACAO_MINIMA_SEM_PRODUTOS     = float(os.getenv("OCUPACAO_MINIMA_SEM_PRODUTOS", "0.15"))

PALAVRAS_IGNORAR = {
    "VALOR KM","TAMANHO CAMINHAO","TAMANHO CAMINHÃO",
    "CALCULO DE FRETE POR TAMANHO DE PEÇA","CÁLCULO DE FRETE POR TAMANHO DE PEÇA"
}

# Estimativa por UF (último fallback)
KM_APROX_POR_UF = {
    "RS":150,"SC":450,"PR":700,"SP":1100,"RJ":1500,"MG":1600,"ES":1800,
    "MS":1600,"MT":2200,"DF":2000,"GO":2100,"TO":2500,"BA":2600,"SE":2700,
    "AL":2800,"PE":3000,"PB":3100,"RN":3200,"CE":3400,"PI":3300,"MA":3500,
    "PA":3800,"AP":4100,"AM":4200,"RO":4000,"AC":4300,"RR":4500,
}

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

# Regras municipais fallback (exemplo)
FALLBACK_MUNICIPIOS = [
    {"uf":"MS","municipio":"CAMPO GRANDE","cep_ini":"79000000","cep_fim":"79199999","km": 25},
    {"uf":"RS","municipio":"FREDERICO WESTPHALEN","cep_ini":"98400000","cep_fim":"98419999","km": 10},
]

app = Flask(__name__)

# ==========================
# HELPERS
# ==========================
def limpar_texto(nome: Any) -> str:
    if not isinstance(nome, str): return ""
    return " ".join(nome.replace("\n"," ").split()).strip()

def so_digitos(cep: Any) -> str:
    s = re.sub(r"\D","", str(cep or ""))
    return s[:8] if len(s) >= 8 else s.zfill(8)

def uf_por_cep(cep8: str) -> Optional[str]:
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

def xml_response(xml_str: str) -> Response:
    r = Response(xml_str, status=200)
    r.headers["Content-Type"] = "text/xml; charset=utf-8"
    r.headers["Cache-Control"] = "no-store"
    return r

def get_json_safe() -> Dict[str, Any]:
    try:
        if request.is_json:
            data = request.get_json(silent=True) or {}
            return data if isinstance(data, dict) else {}
    except: pass
    return {}

def get_param(*keys: str, default: Optional[str] = "") -> str:
    """
    Busca em args, form e JSON (nessa ordem). Suporta aliases.
    """
    data_json = get_json_safe()
    for k in keys:
        if k in request.args and str(request.args.get(k)).strip():   return str(request.args.get(k)).strip()
        if k in request.form and str(request.form.get(k)).strip():   return str(request.form.get(k)).strip()
        if k in data_json and str(data_json.get(k)).strip():         return str(data_json.get(k)).strip()
    return default or ""

# ==========================
# PLANILHA
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

# --------- Faixas CEP -> KM ----------
def coletar_faixas_cep_km(xls: pd.ExcelFile) -> List[Tuple[str,str,float]]:
    faixas: List[Tuple[str,str,float]] = []

    def extrai_cep_limpo(v) -> Optional[str]:
        if pd.isna(v): return None
        s = re.sub(r'[.\-\s]', '', str(v).strip())
        if len(s) == 8 and s.isdigit(): return s
        return None

    def extrai_km_val(v) -> Optional[float]:
        if pd.isna(v): return None
        m = re.search(r'[-+]?\d[\d\.\,]*', str(v))
        if not m: return None
        num = m.group(0).replace('.','').replace(',','.')
        try:
            f = float(num)
            if 10 <= f <= 5000: return f
        except: pass
        return None

    abas = ["D"] + [s for s in xls.sheet_names if s != "D"]
    for aba in abas:
        try:
            df = pd.read_excel(xls, aba, dtype=str, header=None)
            if df.empty: continue
            for i in range(len(df.columns) - 2):
                col_ini, col_fim, col_km = df.iloc[:, i], df.iloc[:, i+1], df.iloc[:, i+2]
                ok = False
                for idx in range(len(df)):
                    a = extrai_cep_limpo(col_ini.iloc[idx])
                    b = extrai_cep_limpo(col_fim.iloc[idx])
                    k = extrai_km_val(col_km.iloc[idx])
                    if a and b and k:
                        faixas.append((a, b, k)); ok = True
                if ok: break
            if len(faixas) > 10: break
        except: pass

    uniq = {}
    for a,b,k in faixas: uniq[(a,b)] = k
    out = [(a,b,k) for (a,b),k in uniq.items()]
    out.sort(key=lambda x:(x[0],x[1]))
    return out

def km_por_cep(faixas: List[Tuple[str,str,float]], cep_dest: str) -> Tuple[float, str]:
    d = so_digitos(cep_dest)
    if len(d) != 8: return DEFAULT_KM, "default"
    if faixas:
        n = int(d)
        for a,b,k in faixas:
            if int(a) <= n <= int(b): return float(k), "faixa"
    uf = uf_por_cep(d)
    if uf and uf in KM_APROX_POR_UF: return float(KM_APROX_POR_UF[uf]), "uf_fallback"
    return DEFAULT_KM, "default"

# --------- REGRAS POR MUNICÍPIO ----------
ALIASES_MUNI = {
    "uf": {"uf","estado"}, "municipio": {"municipio","município","cidade"},
    "cep_ini": {"cep_ini","inicio","início","de","start"},
    "cep_fim": {"cep_fim","final","ate","até","to","end"},
    "km": {"km","dist","distancia","distância"},
    "valor_km": {"valor_km","valor km","vl_km"},
    "tam_caminhao": {"tamanho_caminhao","tam_caminhao","tam caminhao","tam caminhão"},
    "fator_mult": {"fator_mult","fator","multiplicador"},
    "pedagio": {"pedagio","pedágio"},
    "acrescimo_pct": {"acrescimo_pct","acréscimo_pct","acrescimo","acréscimo","percentual"},
    "min_frete": {"min_frete","mínimo","frete_min","valor_minimo"},
}
def _match_col(header: List[str], targets: set[str]) -> Optional[int]:
    for i, c in enumerate(header):
        n = limpar_texto(str(c)).lower()
        if any(t in n for t in targets): return i
    return None

def carregar_regras_municipio(xls: pd.ExcelFile) -> List[Dict[str, Any]]:
    if "REGRAS_MUNICIPIO" not in xls.sheet_names: return []
    df = pd.read_excel(xls, "REGRAS_MUNICIPIO", header=0, dtype=str).fillna("")
    if df.empty: return []
    header = [str(x) for x in df.columns]
    idx = {k:_match_col(header, v) for k,v in ALIASES_MUNI.items()}
    regras = []
    for row in df.itertuples(index=False):
        vals = list(row)
        def get(col):
            j = idx[col]
            return (vals[j] if j is not None else "").strip()
        def get_num(col):
            s = get(col)
            m = re.search(r'[-+]?\d[\d\.\,]*', s)
            if not m: return None
            num = m.group(0).replace('.','').replace(',','.')
            try:
                f = float(num);  return f if math.isfinite(f) else None
            except: return None
        cep_ini = so_digitos(get("cep_ini")); cep_fim = so_digitos(get("cep_fim"))
        if len(cep_ini)!=8 or len(cep_fim)!=8: continue
        regras.append({
            "uf": limpar_texto(get("uf")).upper(),
            "municipio": limpar_texto(get("municipio")).upper(),
            "cep_ini": cep_ini, "cep_fim": cep_fim,
            "km": get_num("km"),
            "valor_km": get_num("valor_km"),
            "tam_caminhao": get_num("tam_caminhao"),
            "fator_mult": get_num("fator_mult"),
            "pedagio": get_num("pedagio"),
            "acrescimo_pct": get_num("acrescimo_pct"),
            "min_frete": get_num("min_frete"),
        })
    regras.sort(key=lambda r: (r["cep_ini"], r["cep_fim"]))
    return regras

def buscar_regra_municipio(regras_muni: List[Dict[str, Any]], cep_dest: str) -> Optional[Dict[str, Any]]:
    d = so_digitos(cep_dest)
    if len(d)!=8: return None
    n = int(d)
    for r in regras_muni:
        if int(r["cep_ini"]) <= n <= int(r["cep_fim"]): return r
    return None

# ==========================
# CARREGAMENTO
# ==========================
def carregar_tudo() -> Dict[str, Any]:
    try:
        xls = pd.ExcelFile(ARQ_PLANILHA)
        consts     = carregar_constantes(xls)
        cadastro   = carregar_cadastro_produtos(xls)
        catalogo   = montar_catalogo_tamanho(cadastro)
        faixas     = coletar_faixas_cep_km(xls)
        regras_mun = carregar_regras_municipio(xls) or FALLBACK_MUNICIPIOS
        print(f"[OK] Planilha carregada: {len(catalogo)} produtos, {len(faixas)} faixas, {len(regras_mun)} regras_muni")
        return {"consts": consts, "catalogo": catalogo, "faixas": faixas, "regras_municipio": regras_mun}
    except Exception as e:
        print(f"[WARN] Planilha não encontrada: {e}")
        return {"consts":{"VALOR_KM":DEFAULT_VALOR_KM,"TAM_CAMINHAO":DEFAULT_TAM_CAMINHAO},
                "catalogo":{}, "faixas":[], "regras_municipio":FALLBACK_MUNICIPIOS}

DATA = carregar_tudo()

# ==========================
# CÁLCULO
# ==========================
def calcula_valor_item(tamanho_peca_m: float, km: float, valor_km: float, tam_caminhao: float) -> float:
    if tamanho_peca_m <= 0 or tam_caminhao <= 0: return 0.0
    ocup = float(tamanho_peca_m) / float(tam_caminhao)
    return round(float(valor_km) * float(km) * ocup, 2)

def parse_prods(prods_str: str) -> List[Dict[str, Any]]:
    itens: List[Dict[str, Any]] = []
    if not prods_str: return itens
    blocos = []
    for sep in ("/","|","\n"):
        if sep in prods_str:
            blocos = [b for b in prods_str.split(sep) if b.strip()]
            break
    if not blocos: blocos = [prods_str]

    def norm_num(x):
        if x is None: return 0.0
        s = str(x).strip().lower()
        if s in ("","null","none","nan"): return 0.0
        s = s.replace(",", ".")
        try: return float(s)
        except: return 0.0

    def cm_to_m(x):
        if not x or x == 0: return 0.0
        return x/100.0 if x > 20 else x

    for raw in blocos:
        try:
            comp, larg, alt, cub, qty, peso, codigo, valor = raw.split(";")
            item = {
                "comp": cm_to_m(norm_num(comp)),
                "larg": cm_to_m(norm_num(larg)),
                "alt":  cm_to_m(norm_num(alt)),
                "cub":  norm_num(cub),
                "qty":  int(norm_num(qty)) if norm_num(qty)>0 else 1,
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
# XML builders
# ==========================
def xml_cotacao(valor: float, km: float, uf: Optional[str], fonte: str, itens_xml: str, prazo_min=4, prazo_max=7, obs:str="") -> str:
    prazo = max(prazo_min, (prazo_min + prazo_max)//2)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<cotacao>
  <resultado>
    <codigo>BAKOF</codigo>
    <transportadora>{TRANSPORTADORA_NOME}</transportadora>
    <servico>Transporte</servico>
    <transporte>TERRESTRE</transporte>
    <valor>{valor:.2f}</valor>
    <prazo>{int(prazo)}</prazo>
    <prazo_min>{int(prazo_min)}</prazo_min>
    <prazo_max>{int(prazo_max)}</prazo_max>
    <entrega_domiciliar>1</entrega_domiciliar>
    <detalhes>
      <origem>{CD_ORIGEM}</origem>
      <cep_origem>{so_digitos(CEP_ORIGEM)}</cep_origem>
      <km>{km:.1f}</km>
      <uf>{uf or 'N/A'}</uf>
      <fonte_km>{fonte}</fonte_km>
      {obs}
      <itens>{itens_xml}</itens>
    </detalhes>
  </resultado>
</cotacao>"""

def xml_erro(mensagem: str, cep:str="", obs:str="") -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<cotacao>
  <resultado>
    <codigo>BAKOF</codigo>
    <transportadora>{TRANSPORTADORA_NOME}</transportadora>
    <servico>Transporte</servico>
    <transporte>TERRESTRE</transporte>
    <valor>{DEFAULT_VALOR_FRETE:.2f}</valor>
    <prazo>10</prazo>
    <prazo_min>7</prazo_min>
    <prazo_max>15</prazo_max>
    <entrega_domiciliar>1</entrega_domiciliar>
    <erro>{mensagem}</erro>
    <detalhes>
      <origem>{CD_ORIGEM}</origem>
      <cep_origem>{so_digitos(CEP_ORIGEM)}</cep_origem>
      <cep_consultado>{so_digitos(cep)}</cep_consultado>
      {obs}
    </detalhes>
  </resultado>
</cotacao>"""

# ==========================
# ENDPOINTS
# ==========================
@app.route("/health")
def health():
    return jsonify({
        "ok": True,
        "cd_origem": CD_ORIGEM,
        "cep_origem": CEP_ORIGEM,
        "valores": DATA["consts"],
        "itens_catalogo": len(DATA["catalogo"]),
        "faixas_cep_km": len(DATA["faixas"]),
        "regras_municipio": len(DATA.get("regras_municipio", [])),
        "amostra_faixas": [{"ini": a, "fim": b, "km": k} for a,b,k in DATA["faixas"][:5]],
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
    # Token opcional: só bloqueia se vier e estiver errado
    token = get_param("token", default="")
    if token and token != TOKEN_SECRETO:
        return xml_response(xml_erro("Token inválido"))

    cep_dest = get_param("cep_destino","cep","cepDestino", default="")
    prods    = get_param("prods","produtos","products", default="")
    km_param = get_param("km", default="")

    if not cep_dest:
        return xml_response(xml_erro("Parâmetro 'cep_destino' (ou 'cep') ausente"))

    # Constantes base
    valor_km     = DATA["consts"].get("VALOR_KM", DEFAULT_VALOR_KM)
    tam_caminhao = DATA["consts"].get("TAM_CAMINHAO", DEFAULT_TAM_CAMINHAO)

    # Overrides
    try:
        v_override = get_param("valor_km","vl_km", default="")
        if v_override: valor_km = float(str(v_override).replace(",", "."))
        t_override = get_param("tam_caminhao","tamanho_caminhao", default="")
        if t_override: tam_caminhao = float(str(t_override).replace(",", "."))
    except: pass

    # KM base
    km = None
    km_fonte = "default"

    # 0) parâmetro direto
    if km_param:
        try:
            km = max(1.0, float(str(km_param).replace(",", ".")))
            km_fonte = "param"
        except: km = None

    # 1) regra municipal
    regra = None
    if km is None:
        regra = buscar_regra_municipio(DATA.get("regras_municipio", []), cep_dest)
        if regra:
            if regra.get("km"): km, km_fonte = float(regra["km"]), "municipio"
            if regra.get("valor_km"): valor_km = float(regra["valor_km"])
            if regra.get("tam_caminhao"): tam_caminhao = float(regra["tam_caminhao"])
            fator_mult = regra.get("fator_mult"); pedagio = regra.get("pedagio")
            acresc_pct = regra.get("acrescimo_pct"); min_frete = regra.get("min_frete")
        else:
            fator_mult = pedagio = acresc_pct = min_frete = None
    else:
        fator_mult = pedagio = acresc_pct = min_frete = None

    # 2) faixa de CEP / UF
    if km is None:
        km, km_fonte = km_por_cep(DATA.get("faixas", []), cep_dest)

    # Se não vier prods, devolve fallback em 200
    if not prods:
        uf = uf_por_cep(so_digitos(cep_dest))
        if FALLBACK_VALOR_FIXO_SEM_PRODUTOS:
            return xml_response(xml_cotacao(DEFAULT_VALOR_FRETE, km, uf, km_fonte, itens_xml="", obs="<obs>Sem produtos no payload - valor fixo</obs>"))
        else:
            v_est = round(valor_km * km * OCUPACAO_MINIMA_SEM_PRODUTOS, 2)
            return xml_response(xml_cotacao(v_est, km, uf, km_fonte, itens_xml="", obs=f"<ocupacao_minima>{OCUPACAO_MINIMA_SEM_PRODUTOS:.2f}</ocupacao_minima>"))

    itens = parse_prods(prods)
    if not itens:
        uf = uf_por_cep(so_digitos(cep_dest))
        return xml_response(xml_cotacao(DEFAULT_VALOR_FRETE, km, uf, km_fonte, itens_xml="", obs="<obs>Produtos inválidos - valor fixo</obs>"))

    total = 0.0
    itens_xml = []
    for it in itens:
        nome = it["codigo"] or "Item"
        # catálogo por nome (se existir), senão usa maior dimensão
        tam_catalogo = DATA["catalogo"].get(nome)
        if tam_catalogo is None:
            tam_catalogo = max(it["comp"], it["larg"], it["alt"])
            if tam_catalogo == 0:
                tam_catalogo = 2.0  # evita zero
        v_unit = calcula_valor_item(tam_catalogo, km, valor_km, tam_caminhao)
        v_tot  = v_unit * max(1, it["qty"])
        total += v_tot
        itens_xml.append(f"""
      <item>
        <codigo>{nome}</codigo>
        <tamanho_metros>{tam_catalogo:.3f}</tamanho_metros>
        <km>{km:.1f}</km>
        <valor_unitario>{v_unit:.2f}</valor_unitario>
        <valor_total>{v_tot:.2f}</valor_total>
      </item>""")

    # Ajustes municipais
    if regra:
        if fator_mult: total = total * float(fator_mult)
        if acresc_pct: total = total * (1.0 + float(acresc_pct)/100.0)
        if pedagio:    total = total + float(pedagio)
        if min_frete and float(min_frete) > 0: total = max(total, float(min_frete))

    uf = uf_por_cep(so_digitos(cep_dest))
    xml = xml_cotacao(round(total,2), km, uf, km_fonte, "".join(itens_xml),
                      obs=f"<debug fonte_km='{km_fonte}' valor_km='{valor_km}' tam_caminhao='{tam_caminhao}' muni_regra={'SIM' if regra else 'NAO'} />")
    return xml_response(xml)

# Rota raiz — útil para ping
@app.route("/", methods=["GET"])
def raiz():
    return jsonify({
        "api": "Frete Bakof",
        "versao": "4.3",
        "cd_origem": CD_ORIGEM,
        "cep_origem": CEP_ORIGEM,
        "endpoints": ["/frete", "/frete/tray-debug", "/health"]
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT","8000")), debug=True)
