# app.py — API de Frete com FAIXAS DE CEP (partindo de Campo Grande/MS)
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
CEP_ORIGEM = os.getenv("CEP_ORIGEM", "79108630")  # Campo Grande/MS - CD Principal
ARQ_PLANILHA = os.getenv("PLANILHA_FRETE", "tabela de frete atualizada(2)(Recuperado Automaticamente).xlsx")

DEFAULT_VALOR_KM = float(os.getenv("DEFAULT_VALOR_KM", "7.0"))
DEFAULT_TAM_CAMINHAO = float(os.getenv("DEFAULT_TAM_CAMINHAO", "8.5"))
DEFAULT_KM = float(os.getenv("DEFAULT_KM", "1500.0"))  # KM padrão para CEPs não encontrados
DEFAULT_VALOR_FRETE = float(os.getenv("DEFAULT_VALOR_FRETE", "800.0"))  # Valor fixo para CEPs não encontrados

PALAVRAS_IGNORAR = {
    "VALOR KM", "TAMANHO CAMINHAO", "TAMANHO CAMINHÃO",
    "CALCULO DE FRETE POR TAMANHO DE PEÇA", "CÁLCULO DE FRETE POR TAMANHO DE PEÇA"
}

app = Flask(__name__)

# ==========================
# TABELA DE FAIXAS CEP -> KM (de 100 em 100)
# ORIGEM: CAMPO GRANDE/MS (CEP 79108630)
# IMPORTANTE: Faixas mais específicas devem vir PRIMEIRO
# ==========================
FAIXAS_CEP_KM = [
    # MS - Mato Grosso do Sul (origem: Campo Grande 79108630)
    # ORDEM IMPORTANTE: do mais específico para o mais genérico
    ("79108000", "79108999", 10),    # Campo Grande - CD LOCAL
    ("79000000", "79099999", 20),    # Campo Grande região central
    ("79100000", "79199999", 30),    # Campo Grande região expandida
    ("79200000", "79999999", 100),   # Interior de MS (Dourados, Três Lagoas, etc)
    
    # MT - Mato Grosso
    ("78000000", "78099999", 700),   # Cuiabá
    ("78100000", "78899999", 800),   # Interior MT
    
    # GO - Goiás
    ("74000000", "76799999", 900),   # Goiânia e região
    ("76800000", "76999999", 1000),  # Interior GO
    
    # DF - Distrito Federal
    ("70000000", "72999999", 1100),  # Brasília
    ("73000000", "73699999", 1150),  # Entorno DF
    
    # TO - Tocantins
    ("77000000", "77999999", 1400),  # Tocantins
    
    # PR - Paraná
    ("87000000", "87199999", 500),   # Maringá
    ("86000000", "86199999", 600),   # Londrina
    ("85800000", "85899999", 700),   # Cascavel
    ("84000000", "84999999", 800),   # Ponta Grossa
    ("80000000", "82999999", 900),   # Curitiba e região
    ("83000000", "83999999", 850),   # São José dos Pinhais
    ("85850000", "85869999", 1000),  # Foz do Iguaçu
    ("83400000", "83699999", 950),   # Paranaguá
    
    # SP - São Paulo (região mais próxima de MS)
    ("19000000", "19999999", 800),   # Interior oeste SP
    ("18000000", "18999999", 900),   # Presidente Prudente região
    ("17000000", "17999999", 1000),  # Bauru / Marília
    ("16000000", "16999999", 1100),  # Araçatuba / São José Rio Preto
    ("15000000", "15999999", 1150),  # Sorocaba / Itu
    ("14000000", "14999999", 1200),  # Ribeirão Preto / Araraquara
    ("13000000", "13999999", 1300),  # Campinas / Piracicaba
    ("12000000", "12999999", 1400),  # São José dos Campos / Taubaté
    ("09000000", "09999999", 1450),  # ABC Paulista
    ("01000000", "08999999", 1450),  # São Paulo Capital e Região
    ("11000000", "11999999", 1500),  # Santos / Baixada Santista
    
    # SC - Santa Catarina
    ("89800000", "89899999", 700),   # Chapecó
    ("89500000", "89699999", 800),   # Região Oeste SC
    ("89100000", "89299999", 1000),  # Joinville
    ("89000000", "89099999", 1100),  # Blumenau
    ("88000000", "88099999", 1150),  # Florianópolis
    ("88300000", "88499999", 1200),  # Itajaí / Balneário Camboriú
    ("88700000", "88899999", 1250),  # Criciúma / Sul SC
    
    # RS - Rio Grande do Sul
    ("98000000", "98999999", 1300),  # Norte RS (Frederico Westphalen, Erechim)
    ("99000000", "99099999", 1400),  # Passo Fundo
    ("95000000", "95999999", 1500),  # Caxias do Sul
    ("97000000", "97999999", 1450),  # Santa Maria
    ("93000000", "93999999", 1600),  # Novo Hamburgo / São Leopoldo
    ("92000000", "92999999", 1650),  # Canoas
    ("94000000", "94999999", 1700),  # Gravataí / Alvorada
    ("90000000", "91999999", 1700),  # Porto Alegre e região metropolitana
    ("96000000", "96999999", 1800),  # Pelotas / Rio Grande
    
    # MG - Minas Gerais
    ("38000000", "38999999", 1400),  # Montes Claros / Norte MG
    ("39000000", "39999999", 1350),  # Vale do Jequitinhonha
    ("37000000", "37999999", 1500),  # Sul de Minas
    ("35000000", "35999999", 1600),  # Poços de Caldas / Pouso Alegre
    ("36000000", "36999999", 1650),  # Juiz de Fora
    ("32000000", "34999999", 1700),  # Contagem / Betim
    ("30000000", "31999999", 1750),  # Belo Horizonte
    
    # RJ - Rio de Janeiro
    ("28000000", "28999999", 1700),  # Interior Norte RJ
    ("27000000", "27999999", 1750),  # Interior Sul RJ
    ("25000000", "26999999", 1800),  # Interior / Petrópolis
    ("24000000", "24999999", 1850),  # Niterói / São Gonçalo
    ("20000000", "23999999", 1900),  # Rio de Janeiro Capital
    
    # ES - Espírito Santo
    ("29000000", "29999999", 2000),  # Vitória e região
    
    # BA - Bahia
    ("40000000", "42999999", 2200),  # Salvador
    ("43000000", "48999999", 2100),  # Interior BA (oeste mais próximo)
    
    # Nordeste
    ("49000000", "49999999", 2400),  # SE - Sergipe
    ("57000000", "57999999", 2500),  # AL - Alagoas
    ("50000000", "56999999", 2600),  # PE - Pernambuco
    ("58000000", "58999999", 2700),  # PB - Paraíba
    ("59000000", "59999999", 2800),  # RN - Rio Grande do Norte
    ("60000000", "63999999", 2900),  # CE - Ceará
    ("64000000", "64999999", 2850),  # PI - Piauí
    ("65000000", "65999999", 3000),  # MA - Maranhão
    
    # Norte
    ("69300000", "69399999", 2200),  # RR - Roraima (via MT)
    ("69900000", "69999999", 2400),  # AC - Acre
    ("76800000", "76999999", 2000),  # RO - Rondônia
    ("69000000", "69899999", 2600),  # AM - Amazonas
    ("66000000", "68899999", 2800),  # PA - Pará
    ("68900000", "68999999", 3200),  # AP - Amapá
]

# ==========================
# FUNÇÕES AUXILIARES
# ==========================
def limpar_cep(cep: str) -> str:
    """Remove formatação e retorna 8 dígitos"""
    s = re.sub(r'\D', '', str(cep or ""))
    return s[:8].zfill(8) if s else "00000000"

def buscar_km_por_cep(cep_destino: str) -> Tuple[float, str]:
    """
    Busca KM baseado em faixas de CEP
    Retorna: (km, fonte)
    """
    cep = limpar_cep(cep_destino)
    cep_num = int(cep)
    
    # Busca na tabela de faixas
    for cep_ini, cep_fim, km in FAIXAS_CEP_KM:
        if int(cep_ini) <= cep_num <= int(cep_fim):
            return (float(km), "faixa_cep")
    
    # Fallback por UF
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
    
    # CEP não encontrado - retorna valor padrão
    print(f"[WARN] CEP não encontrado: {cep} - usando valor padrão")
    return (DEFAULT_KM, "cep_nao_encontrado")

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
        "versao": "4.0 - CD Campo Grande/MS",
        "cd_origem": "Campo Grande/MS",
        "cep_origem": CEP_ORIGEM,
        "faixas_cadastradas": len(FAIXAS_CEP_KM),
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
        "cd_origem": "Campo Grande/MS",
        "cep_origem": CEP_ORIGEM,
        "valores": DATA["consts"],
        "produtos_catalogo": len(DATA["catalogo"]),
        "faixas_cep": len(FAIXAS_CEP_KM),
        "default_km": DEFAULT_KM,
        "default_valor_frete": DEFAULT_VALOR_FRETE,
    }

@app.route("/consultar-cep")
def consultar_cep():
    """Endpoint para consultar KM de um CEP específico"""
    cep = request.args.get("cep", "")
    if not cep:
        return {"erro": "Informe o parâmetro 'cep'"}
    
    km, fonte = buscar_km_por_cep(cep)
    uf = uf_por_cep(limpar_cep(cep))
    
    return {
        "cep": limpar_cep(cep),
        "uf": uf,
        "km": km,
        "fonte": fonte,
        "origem": "Campo Grande/MS",
        "valor_fixo_se_nao_encontrado": DEFAULT_VALOR_FRETE if fonte == "cep_nao_encontrado" else None
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

    # Log para debug
    print(f"[DEBUG] CEP Destino: {cep_destino}")
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

    # Busca KM por faixa de CEP
    km, km_fonte = buscar_km_por_cep(cep_destino)
    print(f"[DEBUG] KM calculado: {km} ({km_fonte})")

    # Se CEP não encontrado, pode usar valor fixo ou calcular normalmente
    usar_valor_fixo = (km_fonte == "cep_nao_encontrado")
    
    if usar_valor_fixo:
        print(f"[INFO] CEP não encontrado - aplicando valor fixo de R$ {DEFAULT_VALOR_FRETE:.2f}")
        total = DEFAULT_VALOR_FRETE
        
        # Monta XML com valor fixo
        uf = uf_por_cep(limpar_cep(cep_destino))
        xml = f"""<?xml version="1.0"?>
<cotacao>
  <resultado>
    <codigo>BAKOF</codigo>
    <transportadora>Bakof Logistica</transportadora>
    <transporte>TERRESTRE</transporte>
    <valor>{total:.2f}</valor>
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
        return Response(xml, mimetype="application/xml")

    # Calcula frete por produto (fluxo normal)
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
    <transporte>TERRESTRE</transporte>
    <valor>{total:.2f}</valor>
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
    
    return Response(xml, mimetype="application/xml")

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    print("=" * 70)
    print("🚀 API de Frete Bakof - CD Campo Grande/MS")
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
