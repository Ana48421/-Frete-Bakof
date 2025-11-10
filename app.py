# app.py - API de Frete Bakof - Sistema Robusto e Funcional
import os
import math
import re
from typing import Dict, Any, List, Tuple, Optional
import pandas as pd
from flask import Flask, request, Response

# ============================================================================
# CONFIGURAÇÕES
# ============================================================================
TOKEN_SECRETO = os.getenv("TOKEN_SECRETO", "teste123")
ARQ_PLANILHA = os.getenv("PLANILHA_FRETE", "tabela_frete.xlsx")

DEFAULT_VALOR_KM = float(os.getenv("DEFAULT_VALOR_KM", "7.0"))
DEFAULT_TAM_CAMINHAO = float(os.getenv("DEFAULT_TAM_CAMINHAO", "8.5"))

# Múltiplos centros de distribuição
CENTROS_DISTRIBUICAO = [
    {"nome": "Frederico Westphalen-RS", "sigla": "CD-RS", "cep": "98400000", "uf": "RS"},
    {"nome": "Campo Grande-MS", "sigla": "CD-MS", "cep": "79108630", "uf": "MS"},
    {"nome": "Tauá-CE", "sigla": "CD-CE", "cep": "63660000", "uf": "CE"},
    {"nome": "Montes Claros-MG", "sigla": "CD-MG", "cep": "39404627", "uf": "MG"},
]

app = Flask(__name__)

# ============================================================================
# TABELA DE DISTÂNCIAS POR MUNICÍPIO (BASE DE DADOS LOCAL)
# ============================================================================

# Distâncias de Frederico Westphalen-RS
DISTANCIAS_FREDERICO_WESTPHALEN = {
    # RS
    "98400000-98419999": 10,   # Local
    "98300000-98499999": 50,   # Região
    "99700000-99799999": 100,  # Erechim
    "99000000-99199999": 200,  # Passo Fundo
    "95000000-95999999": 300,  # Caxias do Sul
    "97000000-97999999": 300,  # Santa Maria
    "93000000-93999999": 400,  # Novo Hamburgo
    "92000000-92999999": 450,  # Canoas
    "90000000-91999999": 500,  # Porto Alegre
    "96000000-96999999": 600,  # Pelotas
    # SC
    "89800000-89899999": 200,  # Chapecó
    "89000000-89299999": 500,  # Blumenau/Joinville
    "88000000-88099999": 600,  # Florianópolis
    # PR
    "85800000-85899999": 300,  # Cascavel
    "87000000-87199999": 600,  # Maringá
    "86000000-86199999": 700,  # Londrina
    "80000000-82999999": 850,  # Curitiba
    # SP
    "01000000-19999999": 1400, # São Paulo
    # Outros estados
    "20000000-28999999": 1800, # RJ
    "29000000-29999999": 1900, # ES
    "30000000-39999999": 1700, # MG
    "40000000-48999999": 2600, # BA
    "79000000-79999999": 1600, # MS
    "78000000-78999999": 2200, # MT
}

# Distâncias de Campo Grande-MS
DISTANCIAS_CAMPO_GRANDE = {
    "79100000-79199999": 10,   # Local
    "79000000-79999999": 50,   # MS
    "78000000-78999999": 300,  # Cuiabá-MT
    "76800000-76999999": 400,  # Rondônia
    "85800000-85899999": 500,  # Cascavel-PR
    "80000000-82999999": 900,  # Curitiba-PR
    "87000000-87199999": 800,  # Maringá-PR
    "01000000-19999999": 1000, # São Paulo
    "30000000-39999999": 1200, # MG
    "70000000-72999999": 800,  # Brasília
    "40000000-48999999": 2000, # BA
    "90000000-99999999": 1500, # RS
}

# Distâncias de Tauá-CE
DISTANCIAS_TAUA = {
    "63660000-63669999": 10,   # Local
    "63600000-63699999": 50,   # Região
    "60000000-63999999": 200,  # Ceará
    "64000000-64999999": 250,  # Piauí
    "59000000-59999999": 300,  # RN
    "58000000-58999999": 350,  # PB
    "50000000-56999999": 400,  # PE
    "57000000-57999999": 450,  # AL
    "49000000-49999999": 500,  # SE
    "65000000-65999999": 300,  # MA
    "40000000-48999999": 800,  # BA
    "30000000-39999999": 1500, # MG
    "01000000-19999999": 2800, # SP
}

# Distâncias de Montes Claros-MG
DISTANCIAS_MONTES_CLAROS = {
    "39400000-39419999": 10,   # Local
    "39000000-39999999": 100,  # Norte MG
    "30000000-38999999": 300,  # BH e região
    "40000000-48999999": 400,  # BA
    "29000000-29999999": 500,  # ES
    "70000000-76999999": 600,  # DF/GO
    "20000000-28999999": 800,  # RJ
    "01000000-19999999": 900,  # SP
    "79000000-79999999": 1200, # MS
    "60000000-63999999": 1400, # CE
    "90000000-99999999": 2000, # RS
}

# Mapa de UF por CEP
UF_RANGES = [
    ("RS", "90000000", "99999999"), ("SC", "88000000", "89999999"),
    ("PR", "80000000", "87999999"), ("SP", "01000000", "19999999"),
    ("RJ", "20000000", "28999999"), ("ES", "29000000", "29999999"),
    ("MG", "30000000", "39999999"), ("BA", "40000000", "48999999"),
    ("SE", "49000000", "49999999"), ("PE", "50000000", "56999999"),
    ("AL", "57000000", "57999999"), ("PB", "58000000", "58999999"),
    ("RN", "59000000", "59999999"), ("CE", "60000000", "63999999"),
    ("PI", "64000000", "64999999"), ("MA", "65000000", "65999999"),
    ("PA", "66000000", "68999999"), ("AP", "68900000", "68999999"),
    ("AM", "69000000", "69899999"), ("AC", "69900000", "69999999"),
    ("RR", "69300000", "69399999"), ("DF", "70000000", "72999999"),
    ("GO", "72800000", "76999999"), ("TO", "77000000", "77999999"),
    ("MT", "78000000", "78999999"), ("MS", "79000000", "79999999"),
]

# ============================================================================
# FUNÇÕES AUXILIARES
# ============================================================================

def limpar_cep(cep: str) -> str:
    """Remove formatação e retorna 8 dígitos"""
    s = re.sub(r'\D', '', str(cep or ""))
    return s[:8].zfill(8) if len(s) >= 8 else "00000000"

def uf_por_cep(cep: str) -> Optional[str]:
    """Retorna UF baseado no CEP"""
    cep_limpo = limpar_cep(cep)
    try:
        cep_num = int(cep_limpo)
        for uf, inicio, fim in UF_RANGES:
            if int(inicio) <= cep_num <= int(fim):
                return uf
    except:
        pass
    return None

def buscar_km_por_faixa(tabela: Dict[str, int], cep: str) -> Optional[int]:
    """Busca KM em uma tabela de faixas"""
    cep_limpo = limpar_cep(cep)
    try:
        cep_num = int(cep_limpo)
        for faixa, km in tabela.items():
            inicio, fim = faixa.split("-")
            if int(inicio) <= cep_num <= int(fim):
                return km
    except:
        pass
    return None

def escolher_melhor_cd(cep_destino: str) -> Tuple[str, str, str, int, str]:
    """
    Escolhe o centro de distribuição mais próximo
    Retorna: (nome_cd, sigla_cd, cep_cd, km, fonte)
    """
    resultados = []
    
    # Testa cada centro de distribuição
    tabelas = [
        (CENTROS_DISTRIBUICAO[0], DISTANCIAS_FREDERICO_WESTPHALEN),
        (CENTROS_DISTRIBUICAO[1], DISTANCIAS_CAMPO_GRANDE),
        (CENTROS_DISTRIBUICAO[2], DISTANCIAS_TAUA),
        (CENTROS_DISTRIBUICAO[3], DISTANCIAS_MONTES_CLAROS),
    ]
    
    for cd, tabela in tabelas:
        km = buscar_km_por_faixa(tabela, cep_destino)
        if km:
            resultados.append((cd["nome"], cd["sigla"], cd["cep"], km, "tabela_cd"))
    
    # Se encontrou, retorna o mais próximo
    if resultados:
        resultados.sort(key=lambda x: x[3])  # Ordena por KM
        return resultados[0]
    
    # Fallback por UF
    uf = uf_por_cep(cep_destino)
    km_uf = {
        "RS": 150, "SC": 450, "PR": 700, "SP": 1100, "RJ": 1500,
        "MG": 1600, "ES": 1800, "MS": 1600, "MT": 2200, "DF": 2000,
        "GO": 2100, "TO": 2500, "BA": 2600, "SE": 2700, "AL": 2800,
        "PE": 3000, "PB": 3100, "RN": 3200, "CE": 3400, "PI": 3300,
        "MA": 3500, "PA": 3800, "AP": 4100, "AM": 4200, "RO": 4000,
        "AC": 4300, "RR": 4500,
    }
    km = km_uf.get(uf, 450)
    return (CENTROS_DISTRIBUICAO[0]["nome"], CENTROS_DISTRIBUICAO[0]["sigla"], CENTROS_DISTRIBUICAO[0]["cep"], km, f"fallback_uf_{uf}")

# ============================================================================
# FUNÇÕES DA PLANILHA
# ============================================================================

def limpar_texto(texto: Any) -> str:
    if not isinstance(texto, str):
        return ""
    return " ".join(texto.replace("\n", " ").split()).strip()

def extrair_numero(valor) -> Optional[float]:
    """Extrai número de uma célula"""
    if valor is None or pd.isna(valor):
        return None
    s = str(valor).strip().upper().replace(",", ".")
    s = re.sub(r'[^\d\.]', '', s)
    try:
        f = float(s)
        return f if math.isfinite(f) and f > 0 else None
    except:
        return None

def carregar_constantes(xls: pd.ExcelFile) -> Dict[str, float]:
    """Carrega VALOR_KM e TAMANHO_CAMINHAO da planilha"""
    valor_km = DEFAULT_VALOR_KM
    tam_caminhao = DEFAULT_TAM_CAMINHAO
    
    for aba in ["BASE_CALCULO", "D", "CONSTANTES", "BASE"]:
        if aba not in xls.sheet_names:
            continue
        try:
            df = pd.read_excel(xls, aba, header=None)
            for _, row in df.iterrows():
                texto_linha = " ".join([str(v).upper() for v in row if pd.notna(v)])
                
                if "VALOR" in texto_linha and "KM" in texto_linha:
                    for v in row:
                        num = extrair_numero(v)
                        if num and 3 <= num <= 50:
                            valor_km = num
                            break
                
                if "TAMANHO" in texto_linha and "CAMINH" in texto_linha:
                    for v in row:
                        num = extrair_numero(v)
                        if num and 3 <= num <= 20:
                            tam_caminhao = num
                            break
        except Exception as e:
            print(f"[WARN] Erro ao ler aba {aba}: {e}")
    
    return {"VALOR_KM": valor_km, "TAM_CAMINHAO": tam_caminhao}

def carregar_produtos(xls: pd.ExcelFile) -> Dict[str, float]:
    """Carrega catálogo de produtos com diâmetros"""
    for aba in ["CADASTRO_PRODUTO", "CADASTRO", "PRODUTOS"]:
        if aba not in xls.sheet_names:
            continue
        try:
            df = pd.read_excel(xls, aba, header=None)
            # Assume: col 0 ou 2 = nome, col 3 = dim1, col 4 = dim2
            catalogo = {}
            
            for _, row in df.iterrows():
                try:
                    # Tenta diferentes estruturas
                    nome = limpar_texto(row[2] if len(row) > 2 else row[0])
                    dim1 = extrair_numero(row[3] if len(row) > 3 else 0) or 0
                    dim2 = extrair_numero(row[4] if len(row) > 4 else 0) or 0
                    
                    if nome and (dim1 > 0 or dim2 > 0):
                        # Usa a maior dimensão
                        catalogo[nome] = max(dim1, dim2)
                except:
                    continue
            
            if catalogo:
                print(f"[OK] Carregados {len(catalogo)} produtos da planilha")
                return catalogo
        except Exception as e:
            print(f"[WARN] Erro ao ler aba {aba}: {e}")
    
    return {}

def carregar_dados() -> Dict[str, Any]:
    """Carrega todos os dados da planilha"""
    try:
        xls = pd.ExcelFile(ARQ_PLANILHA)
        consts = carregar_constantes(xls)
        produtos = carregar_produtos(xls)
        return {"consts": consts, "produtos": produtos}
    except Exception as e:
        print(f"[INFO] Usando valores padrão (planilha não encontrada)")
        return {
            "consts": {"VALOR_KM": DEFAULT_VALOR_KM, "TAM_CAMINHAO": DEFAULT_TAM_CAMINHAO},
            "produtos": {}
        }

DATA = carregar_dados()

# ============================================================================
# CÁLCULO DE FRETE
# ============================================================================

def calcular_valor_frete(tamanho_m: float, km: float, valor_km: float, tam_caminhao: float) -> float:
    """
    Fórmula: (tamanho_produto / tamanho_caminhão) × valor_km × km
    """
    if tamanho_m <= 0 or tam_caminhao <= 0:
        return 0.0
    
    ocupacao = tamanho_m / tam_caminhao
    valor = ocupacao * valor_km * km
    return round(valor, 2)

def parse_produtos(prods_str: str) -> List[Dict[str, Any]]:
    """Parse produtos formato Tray: comp;larg;alt;cub;qty;peso;codigo;valor"""
    itens = []
    
    # Separa múltiplos produtos
    blocos = []
    for sep in ["/", "|"]:
        if sep in prods_str:
            blocos = [b.strip() for b in prods_str.split(sep) if b.strip()]
            break
    if not blocos:
        blocos = [prods_str]
    
    for bloco in blocos:
        try:
            partes = bloco.split(";")
            if len(partes) < 8:
                print(f"[WARN] Produto com menos de 8 campos: {bloco}")
                continue
            
            comp = float(partes[0].replace(",", ".") or 0)
            larg = float(partes[1].replace(",", ".") or 0)
            alt = float(partes[2].replace(",", ".") or 0)
            qty = int(float(partes[4].replace(",", ".") or 1))
            codigo = partes[6].strip()
            
            # Converte cm para metros se necessário
            comp = comp / 100 if comp > 20 else comp
            larg = larg / 100 if larg > 20 else larg
            alt = alt / 100 if alt > 20 else alt
            
            itens.append({
                "comp": comp,
                "larg": larg,
                "alt": alt,
                "qty": max(1, qty),
                "codigo": codigo or "Item"
            })
            
        except Exception as e:
            print(f"[ERROR] Erro ao processar: {bloco} - {e}")
    
    return itens

# ============================================================================
# ENDPOINTS
# ============================================================================

@app.route("/", methods=["GET"])
def index():
    """Rota principal - redireciona para frete se tiver parâmetros"""
    if request.args.get("cep_destino"):
        return calcular_frete()
    
    return {
        "status": "online",
        "api": "Bakof Frete v5.0",
        "centros_distribuicao": len(CENTROS_DISTRIBUICAO),
        "endpoints": {
            "/": "Calcular frete (Tray)",
            "/frete": "Calcular frete",
            "/health": "Status da API",
            "/consultar": "Consultar KM para um CEP"
        }
    }

@app.route("/health")
def health():
    return {
        "ok": True,
        "versao": "5.0",
        "centros": [f"{cd['sigla']} - {cd['nome']}" for cd in CENTROS_DISTRIBUICAO],
        "produtos_cadastrados": len(DATA["produtos"]),
        "valor_km": DATA["consts"]["VALOR_KM"],
        "tamanho_caminhao": DATA["consts"]["TAM_CAMINHAO"]
    }

@app.route("/consultar")
def consultar():
    """Consulta KM para um CEP"""
    cep = request.args.get("cep", "")
    if not cep:
        return {"erro": "Informe o parâmetro 'cep'"}, 400
    
    nome_cd, sigla_cd, cep_cd, km, fonte = escolher_melhor_cd(cep)
    uf = uf_por_cep(cep)
    
    return {
        "cep_destino": limpar_cep(cep),
        "uf": uf,
        "centro_distribuicao": f"{sigla_cd} - {nome_cd}",
        "sigla_cd": sigla_cd,
        "nome_cd": nome_cd,
        "cep_origem": cep_cd,
        "distancia_km": km,
        "fonte": fonte
    }

@app.route("/frete", methods=["GET"])
def calcular_frete():
    """Endpoint principal de cálculo de frete"""
    
    # Autenticação (opcional)
    token = request.args.get("token", "")
    if token and token != TOKEN_SECRETO:
        return Response("Token inválido", status=403)
    
    # Parâmetros obrigatórios
    cep_destino = request.args.get("cep_destino", "")
    prods = request.args.get("prods", "")
    
    print(f"\n{'='*60}")
    print(f"[REQUEST] CEP: {cep_destino}, Produtos: {prods[:50]}...")
    
    if not cep_destino:
        return Response("Parâmetro 'cep_destino' obrigatório", status=400)
    if not prods:
        return Response("Parâmetro 'prods' obrigatório", status=400)
    
    # Parse produtos
    itens = parse_produtos(prods)
    if not itens:
        return Response("Nenhum produto válido", status=400)
    
    print(f"[INFO] Produtos parseados: {len(itens)}")
    
    # Constantes
    valor_km = DATA["consts"]["VALOR_KM"]
    tam_caminhao = DATA["consts"]["TAM_CAMINHAO"]
    
    # Permite override
    if request.args.get("valor_km"):
        valor_km = float(request.args["valor_km"].replace(",", "."))
    if request.args.get("tam_caminhao"):
        tam_caminhao = float(request.args["tam_caminhao"].replace(",", "."))
    
    # Escolhe melhor CD
    nome_cd, sigla_cd, cep_cd, km, fonte = escolher_melhor_cd(cep_destino)
    print(f"[{sigla_cd}] {nome_cd} ({cep_cd}) - {km} km ({fonte})")
    
    # Calcula frete por produto
    total = 0.0
    itens_xml = []
    
    for item in itens:
        codigo = item["codigo"]
        
        # Busca tamanho no catálogo
        tamanho = DATA["produtos"].get(codigo)
        if not tamanho:
            # Usa maior dimensão
            tamanho = max(item["comp"], item["larg"], item["alt"])
            if tamanho == 0:
                tamanho = 2.0  # Padrão
        
        print(f"[ITEM] {codigo}: {tamanho:.2f}m x {item['qty']}un")
        
        # Calcula valor
        valor_unit = calcular_valor_frete(tamanho, km, valor_km, tam_caminhao)
        valor_total = valor_unit * item["qty"]
        total += valor_total
        
        print(f"       R$ {valor_unit:.2f} x {item['qty']} = R$ {valor_total:.2f}")
        
        itens_xml.append(f"""
      <item>
        <codigo>{codigo}</codigo>
        <quantidade>{item['qty']}</quantidade>
        <tamanho_m>{tamanho:.3f}</tamanho_m>
        <valor_unit>{valor_unit:.2f}</valor_unit>
        <valor_total>{valor_total:.2f}</valor_total>
      </item>""")
    
    print(f"[TOTAL] R$ {total:.2f}")
    print(f"{'='*60}\n")
    
    # Resposta XML (formato Tray)
    uf = uf_por_cep(cep_destino)
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<cotacao>
  <resultado>
    <codigo>BAKOF</codigo>
    <transportadora>Bakof Logistica - {sigla_cd}</transportadora>
    <servico>Transporte Rodoviario</servico>
    <transporte>TERRESTRE</transporte>
    <valor>{total:.2f}</valor>
    <prazo_min>4</prazo_min>
    <prazo_max>7</prazo_max>
    <entrega_domiciliar>1</entrega_domiciliar>
    <detalhes>
      <centro_distribuicao>{sigla_cd}</centro_distribuicao>
      <origem>{nome_cd}</origem>
      <cep_origem>{cep_cd}</cep_origem>
      <distancia_km>{km}</distancia_km>
      <uf_destino>{uf or 'N/A'}</uf_destino>
      <valor_por_km>{valor_km:.2f}</valor_por_km>
      <itens>{"".join(itens_xml)}
      </itens>
    </detalhes>
  </resultado>
</cotacao>"""
    
    return Response(xml, mimetype="application/xml")

# ============================================================================
# INICIALIZAÇÃO
# ============================================================================

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    
    print("\n" + "="*70)
    print("🚀 API DE FRETE BAKOF - SISTEMA OTIMIZADO")
    print("="*70)
    print("📍 Centros de Distribuição:")
    for cd in CENTROS_DISTRIBUICAO:
        print(f"   • {cd['sigla']} - {cd['nome']} ({cd['uf']}) - CEP {cd['cep']}")
    print(f"\n💰 Valor por KM: R$ {DATA['consts']['VALOR_KM']:.2f}")
    print(f"🚛 Tamanho caminhão: {DATA['consts']['TAM_CAMINHAO']:.1f}m")
    print(f"📦 Produtos cadastrados: {len(DATA['produtos'])}")
    print(f"🔑 Token: {TOKEN_SECRETO}")
    print(f"🌐 Servidor: http://0.0.0.0:{port}")
    print(f"\n✨ Sistema escolhe automaticamente o CD mais próximo do destino!")
    print("="*70 + "\n")
    
    app.run(host="0.0.0.0", port=port, debug=False)
