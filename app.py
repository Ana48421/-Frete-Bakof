import os
import requests
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from datetime import datetime
from math import radians, cos, sin, asin, sqrt
from dotenv import load_dotenv

# -----------------------------------------------------------------------------
# BOOT
# -----------------------------------------------------------------------------
load_dotenv()

app = Flask(__name__)
CORS(app)

# -----------------------------------------------------------------------------
# CONFIG
# -----------------------------------------------------------------------------
TOKEN_SECRETO = os.getenv('TOKEN_SECRETO', 'teste123')
DEFAULT_VALOR_KM = float(os.getenv('DEFAULT_VALOR_KM', 7.0))
TRAY_API_URL = os.getenv('TRAY_API_URL', '')
TRAY_API_TOKEN = os.getenv('TRAY_API_TOKEN', '')

HTTP_TIMEOUT = float(os.getenv('HTTP_TIMEOUT', '5.0'))

# -----------------------------------------------------------------------------
# CENTROS DE DISTRIBUIÇÃO
# -----------------------------------------------------------------------------
CENTROS_DISTRIBUICAO = {
    "RS": {
        "nome": "CD Sul - Rio Grande do Sul",
        "cidade": "Frederico Westphalen",
        "uf": "RS",
        "cep": "98400000",
        "codigo_ibge": 4307708,
        "lat": -27.3636,
        "lon": -53.3978,
        "codigo_cd_tray": "CD_RS"
    },
    "SC": {
        "nome": "CD Sudeste - Santa Catarina",
        "cidade": "Joinville",
        "uf": "SC",
        "cep": "89239250",
        "codigo_ibge": 4209102,
        "lat": -26.3045,
        "lon": -48.8487,
        "codigo_cd_tray": "CD_SC"
    },
    "MG": {
        "nome": "CD Sudeste - Minas Gerais",
        "cidade": "Montes Claros",
        "uf": "MG",
        "cep": "39404627",
        "codigo_ibge": 3143302,
        "lat": -16.7350,
        "lon": -43.8619,
        "codigo_cd_tray": "CD_MG"
    },
    "MS": {
        "nome": "CD Centro-Oeste - Mato Grosso do Sul",
        "cidade": "Campo Grande",
        "uf": "MS",
        "cep": "79108630",
        "codigo_ibge": 5002704,
        "lat": -20.4697,
        "lon": -54.6201,
        "codigo_cd_tray": "CD_MS"
    },
    "CE": {
        "nome": "CD Nordeste - Ceará",
        "cidade": "Tauá",
        "uf": "CE",
        "cep": "63660000",
        "codigo_ibge": 2313302,
        "lat": -6.0014,
        "lon": -40.2925,
        "codigo_cd_tray": "CD_CE"
    }
}

# -----------------------------------------------------------------------------
# FUNÇÕES AUXILIARES
# -----------------------------------------------------------------------------
def haversine(lat1, lon1, lat2, lon2) -> float:
    """
    Distância em km entre dois pontos (Haversine) + 15% para trajeto rodoviário.
    """
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    km = 6371 * c
    return km * 1.15  # fator rodoviário

def _clean_cep(cep: str) -> str:
    return cep.replace('-', '').replace('.', '').strip()

def buscar_coordenadas_capital(uf):
    capitais = {
        'AC': {'nome': 'Rio Branco', 'lat': -9.9754, 'lon': -67.8249},
        'AL': {'nome': 'Maceió', 'lat': -9.6658, 'lon': -35.7353},
        'AP': {'nome': 'Macapá', 'lat': 0.0389, 'lon': -51.0664},
        'AM': {'nome': 'Manaus', 'lat': -3.1190, 'lon': -60.0217},
        'BA': {'nome': 'Salvador', 'lat': -12.9714, 'lon': -38.5014},
        'CE': {'nome': 'Fortaleza', 'lat': -3.7172, 'lon': -38.5433},
        'DF': {'nome': 'Brasília', 'lat': -15.7939, 'lon': -47.8828},
        'ES': {'nome': 'Vitória', 'lat': -20.3155, 'lon': -40.3128},
        'GO': {'nome': 'Goiânia', 'lat': -16.6869, 'lon': -49.2648},
        'MA': {'nome': 'São Luís', 'lat': -2.5387, 'lon': -44.2825},
        'MT': {'nome': 'Cuiabá', 'lat': -15.6014, 'lon': -56.0979},
        'MS': {'nome': 'Campo Grande', 'lat': -20.4697, 'lon': -54.6201},
        'MG': {'nome': 'Belo Horizonte', 'lat': -19.9167, 'lon': -43.9345},
        'PA': {'nome': 'Belém', 'lat': -1.4558, 'lon': -48.5039},
        'PB': {'nome': 'João Pessoa', 'lat': -7.1195, 'lon': -34.8450},
        'PR': {'nome': 'Curitiba', 'lat': -25.4284, 'lon': -49.2733},
        'PE': {'nome': 'Recife', 'lat': -8.0476, 'lon': -34.8770},
        'PI': {'nome': 'Teresina', 'lat': -5.0892, 'lon': -42.8016},
        'RJ': {'nome': 'Rio de Janeiro', 'lat': -22.9068, 'lon': -43.1729},
        'RN': {'nome': 'Natal', 'lat': -5.7945, 'lon': -35.2110},
        'RS': {'nome': 'Porto Alegre', 'lat': -30.0346, 'lon': -51.2177},
        'RO': {'nome': 'Porto Velho', 'lat': -8.7612, 'lon': -63.9004},
        'RR': {'nome': 'Boa Vista', 'lat': 2.8235, 'lon': -60.6758},
        'SC': {'nome': 'Florianópolis', 'lat': -27.5954, 'lon': -48.5480},
        'SP': {'nome': 'São Paulo', 'lat': -23.5505, 'lon': -46.6333},
        'SE': {'nome': 'Aracaju', 'lat': -10.9472, 'lon': -37.0731},
        'TO': {'nome': 'Palmas', 'lat': -10.2491, 'lon': -48.3243}
    }
    if uf in capitais:
        capital = capitais[uf]
        print(f"[GEO] Fallback capital: {capital['nome']}/{uf}")
        return {
            'municipio': capital['nome'],
            'uf': uf,
            'lat': capital['lat'],
            'lon': capital['lon']
        }
    return None

def buscar_coordenadas_ibge(cep: str):
    """
    Busca coordenadas reais para o CEP.
    1) Tenta BrasilAPI (CEP v2) -> devolve coords quando possível.
    2) ViaCEP (para obter cidade/UF).
    3) Fallback: capital do estado.
    """
    try:
        cep = _clean_cep(cep)
        print(f"[GEO] CEP: {cep}")

        # 1) BrasilAPI CEP v2
        try:
            r = requests.get(f"https://brasilapi.com.br/api/cep/v2/{cep}", timeout=HTTP_TIMEOUT)
            if r.status_code == 200:
                b = r.json()
                uf = b.get('state', '')
                municipio = b.get('city', '')
                loc = b.get('location') or {}
                coords = (loc.get('coordinates') or {}) if isinstance(loc, dict) else {}
                lat = coords.get('latitude')
                lon = coords.get('longitude')
                if lat is not None and lon is not None:
                    lat = float(lat)
                    lon = float(lon)
                    print(f"[GEO] BrasilAPI OK -> {municipio}/{uf} [{lat},{lon}]")
                    return {'municipio': municipio, 'uf': uf, 'lat': lat, 'lon': lon}
                else:
                    print(f"[GEO] BrasilAPI sem coords, vai para ViaCEP fallback…")
                    # segue para ViaCEP
            else:
                print(f"[GEO] BrasilAPI status {r.status_code}, usando fallback…")
        except requests.Timeout:
            print("[GEO] Timeout BrasilAPI")
        except Exception as e:
            print(f"[GEO] Erro BrasilAPI: {e}")

        # 2) ViaCEP para UF / cidade
        try:
            r = requests.get(f"https://viacep.com.br/ws/{cep}/json/", timeout=HTTP_TIMEOUT)
            if r.status_code == 200:
                v = r.json()
                if v.get('erro'):
                    print("[GEO] ViaCEP: CEP não encontrado")
                    return None
                municipio = v.get('localidade', '')
                uf = v.get('uf', '')
                if municipio and uf:
                    # 3) Fallback: capital (sem coords do município)
                    print(f"[GEO] ViaCEP OK sem coords -> {municipio}/{uf}. Indo p/ capital fallback…")
                    cap = buscar_coordenadas_capital(uf)
                    if cap:
                        cap['municipio'] = municipio  # mantém município destino para exibir
                        return cap
            else:
                print(f"[GEO] ViaCEP status {r.status_code}")
        except requests.Timeout:
            print("[GEO] Timeout ViaCEP")
        except Exception as e:
            print(f"[GEO] Erro ViaCEP: {e}")

    except Exception as e:
        print(f"[GEO] Falha inesperada: {e}")

    return None

def verificar_estoque_tray(codigo_produto, cd_codigo):
    """
    Verifica estoque do produto no CD específico via API Tray.
    Se a API não estiver configurada, assume disponível.
    """
    if not TRAY_API_URL or not TRAY_API_TOKEN:
        print(f"[TRAY] API não configurada -> assume disponível")
        return True
    try:
        headers = {
            'Authorization': f'Bearer {TRAY_API_TOKEN}',
            'Content-Type': 'application/json'
        }
        url = f"{TRAY_API_URL.rstrip('/')}/products"
        params = {'reference': codigo_produto}
        r = requests.get(url, headers=headers, params=params, timeout=HTTP_TIMEOUT)
        if r.status_code != 200:
            print(f"[TRAY] Erro buscar produto {codigo_produto}: {r.status_code}")
            return True
        data = r.json() or {}
        products = data.get('products') or []
        if not products:
            print(f"[TRAY] Produto {codigo_produto} não encontrado")
            return True
        produto = products[0]
        campo_estoque = f"stock_{cd_codigo}"
        if campo_estoque in produto:
            estoque = int(produto[campo_estoque])
            print(f"[TRAY] {codigo_produto} @ {cd_codigo} -> {estoque}")
            return estoque > 0
        if 'stock' in produto:
            estoque = int(produto['stock'])
            print(f"[TRAY] {codigo_produto} stock padrão -> {estoque}")
            return estoque > 0
        print("[TRAY] Campo de estoque não encontrado")
        return True
    except Exception as e:
        print(f"[TRAY] Erro estoque: {e}")
        return True

def calcular_distancias_cds(lat_destino, lon_destino):
    distancias = []
    for cd_id, cd_info in CENTROS_DISTRIBUICAO.items():
        distancia = haversine(cd_info['lat'], cd_info['lon'], lat_destino, lon_destino)
        distancias.append({'cd_id': cd_id, 'cd_info': cd_info, 'distancia': distancia})
    distancias.sort(key=lambda x: x['distancia'])
    return distancias

def selecionar_melhor_cd(lat_destino, lon_destino, produtos):
    distancias = calcular_distancias_cds(lat_destino, lon_destino)
    print(f"\n[CALC] Distâncias:")
    for d in distancias:
        print(f"  - {d['cd_info']['nome']}: {d['distancia']:.1f} km")

    for d in distancias:
        cd_info = d['cd_info']
        todos_disponiveis = True
        for produto in produtos:
            codigo = (produto.get('codigo') or '').strip()
            if codigo and not verificar_estoque_tray(codigo, cd_info['codigo_cd_tray']):
                todos_disponiveis = False
                print(f"[CD] {cd_info['nome']}: sem estoque do {codigo}")
                break
        if todos_disponiveis:
            print(f"[CD] ✓ Escolhido: {cd_info['nome']} ({d['distancia']:.1f} km)")
            return {'cd_id': d['cd_id'], 'cd_info': cd_info, 'distancia': d['distancia'], 'tem_estoque': True}

    print(f"[CD] ⚠️ Sem estoque completo, usando mais próximo")
    return {'cd_id': distancias[0]['cd_id'], 'cd_info': distancias[0]['cd_info'], 'distancia': distancias[0]['distancia'], 'tem_estoque': False}

def calcular_prazo_entrega(distancia_km: float) -> int:
    if distancia_km <= 100: return 3
    if distancia_km <= 300: return 5
    if distancia_km <= 600: return 7
    if distancia_km <= 1000: return 10
    return 15

def calcular_valor_frete(distancia_km, peso_total, volume_total, valor_km=None) -> float:
    if valor_km is None:
        valor_km = DEFAULT_VALOR_KM
    valor_base = distancia_km * valor_km
    fator_peso = 1 + (peso_total / 10.0) * 0.05      # +5% a cada 10 kg
    fator_volume = 1 + (volume_total * 0.10)         # +10% por m³
    valor_final = max(valor_base * fator_peso * fator_volume, 50.00)
    return round(valor_final, 2)

def parse_produtos_tray(produtos_str: str):
    """
    Formato: comp;larg;alt;cubagem;quantidade;peso;codigo;valor[/...]
    """
    produtos = []
    try:
        itens = [x.strip() for x in (produtos_str or '').strip('/ ').split('/') if x.strip()]
        for item in itens:
            campos = [c.strip() for c in item.split(';')]
            if len(campos) >= 8:
                try:
                    produtos.append({
                        'comprimento': float(campos[0]),
                        'largura': float(campos[1]),
                        'altura': float(campos[2]),
                        'cubagem': float(campos[3]),
                        'quantidade': int(campos[4]),
                        'peso': float(campos[5]),
                        'codigo': campos[6],
                        'valor': float(campos[7])
                    })
                except ValueError:
                    print(f"[PARSE] Ignorando item inválido: {item}")
        return produtos
    except Exception as e:
        print(f"[PARSE] Erro: {e}")
        return []

# -----------------------------------------------------------------------------
# ENDPOINTS
# -----------------------------------------------------------------------------
@app.route('/frete', methods=['GET', 'POST'])
def calcular_frete():
    try:
        print("\n" + "="*70)
        print(f"📦 NOVA REQUISIÇÃO DE FRETE - {request.method}")
        print("="*70)

        params = request.form.to_dict() if request.method == 'POST' else request.args.to_dict()
        print(f"Parâmetros: {params}")

        cep = params.get('cep_destino') or params.get('cep', '')
        produtos_str = params.get('prods', '')

        if not cep:
            return Response('<?xml version="1.0" encoding="UTF-8"?><error>CEP não informado</error>', mimetype='text/xml'), 400
        if not produtos_str:
            return Response('<?xml version="1.0" encoding="UTF-8"?><error>Produtos não informados</error>', mimetype='text/xml'), 400

        produtos = parse_produtos_tray(produtos_str)
        if not produtos:
            return Response('<?xml version="1.0" encoding="UTF-8"?><error>Formato de produtos inválido</error>', mimetype='text/xml'), 400

        peso_total = sum(p['peso'] * p['quantidade'] for p in produtos)
        volume_total = sum(p['cubagem'] * p['quantidade'] for p in produtos)
        qtd_total = sum(p['quantidade'] for p in produtos)
        print(f"Quantidade total: {qtd_total}, Peso total: {peso_total:.2f} kg")

        coord_destino = buscar_coordenadas_ibge(cep)
        if not coord_destino:
            return Response('<?xml version="1.0" encoding="UTF-8"?><error>CEP inválido ou não encontrado</error>', mimetype='text/xml'), 400

        print(f"[CALC] Destino: {coord_destino['municipio']}/{coord_destino['uf']} ({coord_destino['lat']:.5f},{coord_destino['lon']:.5f})")

        resultado_cd = selecionar_melhor_cd(coord_destino['lat'], coord_destino['lon'], produtos)
        cd_info = resultado_cd['cd_info']
        distancia = resultado_cd['distancia']

        valor_frete = calcular_valor_frete(distancia, peso_total, volume_total)
        prazo = calcular_prazo_entrega(distancia)

        print(f"\n{'='*70}")
        print(f"🏢 CD Selecionado: {cd_info['nome']}")
        print(f"📍 Origem: {cd_info['cidade']}/{cd_info['uf']}")
        print(f"📏 Distância: {distancia:.1f} km")
        print(f"📦 Estoque: {'Disponível' if resultado_cd['tem_estoque'] else 'Verificar'}")
        print(f"💰 Valor: R$ {valor_frete:.2f}")
        print(f"⏱️ Prazo: {prazo} dias")
        print("="*70 + "\n")

        xml_response = f'''<?xml version="1.0" encoding="UTF-8"?>
<shipping>
    <cep>{_clean_cep(cep)}</cep>
    <price>{valor_frete:.2f}</price>
    <delivery_time>{prazo}</delivery_time>
    <message>Frete calculado via {cd_info['nome']}</message>
    <carrier>{cd_info['nome']}</carrier>
    <distance>{distancia:.1f}</distance>
    <origin>{cd_info['cidade']}/{cd_info['uf']}</origin>
</shipping>'''

        return Response(xml_response, mimetype='text/xml')

    except Exception as e:
        print(f"[ERRO] {e}")
        import traceback; traceback.print_exc()
        return Response(f'<?xml version="1.0" encoding="UTF-8"?><error>Erro ao calcular frete: {str(e)}</error>', mimetype='text/xml'), 500

@app.route('/teste', methods=['GET'])
def teste_frete():
    try:
        cep = request.args.get('cep', '')
        produto = request.args.get('produto', 'PROD001')
        if not cep:
            return jsonify({"erro": "Parâmetro 'cep' obrigatório"}), 400

        coord = buscar_coordenadas_ibge(cep)
        if not coord:
            return jsonify({"erro": "CEP inválido"}), 400

        distancias = calcular_distancias_cds(coord['lat'], coord['lon'])

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Teste de Frete - Multi-CD</title>
            <style>
                body {{ font-family: Arial; padding: 20px; background: #f5f5f5; }}
                .container {{ max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; }}
                h1 {{ color: #333; }}
                .info {{ background: #e3f2fd; padding: 15px; border-radius: 5px; margin: 20px 0; }}
                .cd {{ background: #f5f5f5; padding: 15px; margin: 10px 0; border-radius: 5px; border-left: 4px solid #2196F3; }}
                .cd.melhor {{ border-left-color: #4CAF50; background: #e8f5e9; }}
                .stats {{ display: flex; justify-content: space-between; margin: 20px 0; }}
                .stat {{ text-align: center; }}
                .stat-value {{ font-size: 24px; font-weight: bold; color: #2196F3; }}
                .stat-label {{ color: #666; font-size: 14px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🚚 Teste de Frete Multi-CD</h1>
                <div class="info">
                    <h3>📍 Destino</h3>
                    <p><strong>CEP:</strong> {_clean_cep(cep)}</p>
                    <p><strong>Município:</strong> {coord['municipio']}/{coord['uf']}</p>
                    <p><strong>Coordenadas:</strong> {coord['lat']:.4f}, {coord['lon']:.4f}</p>
                    <p><strong>Produto:</strong> {produto}</p>
                </div>
                <h3>📊 Distâncias dos CDs</h3>
        """

        for i, d in enumerate(distancias):
            cd = d['cd_info']
            dist = d['distancia']
            prazo = calcular_prazo_entrega(dist)
            valor = calcular_valor_frete(dist, 10.0, 0.5)
            classe = "cd melhor" if i == 0 else "cd"
            html += f"""
                <div class="{classe}">
                    <h4>{'🏆 ' if i == 0 else ''}{cd['nome']}</h4>
                    <p><strong>Origem:</strong> {cd['cidade']}/{cd['uf']}</p>
                    <div class="stats">
                        <div class="stat">
                            <div class="stat-value">{dist:.0f} km</div>
                            <div class="stat-label">Distância</div>
                        </div>
                        <div class="stat">
                            <div class="stat-value">R$ {valor:.2f}</div>
                            <div class="stat-label">Valor</div>
                        </div>
                        <div class="stat">
                            <div class="stat-value">{prazo} dias</div>
                            <div class="stat-label">Prazo</div>
                        </div>
                    </div>
                </div>
            """

        html += """
            </div>
        </body>
        </html>
        """
        return html
    except Exception as e:
        return jsonify({"erro": str(e)}), 500

@app.route('/cds', methods=['GET'])
def listar_cds():
    cds = []
    for cd_id, cd_info in CENTROS_DISTRIBUICAO.items():
        cds.append({
            'id': cd_id,
            'nome': cd_info['nome'],
            'cidade': cd_info['cidade'],
            'uf': cd_info['uf'],
            'cep': f"{cd_info['cep'][:5]}-{cd_info['cep'][5:]}",
            'lat': cd_info['lat'],
            'lon': cd_info['lon']
        })
    return jsonify({'total': len(cds), 'centros': cds})

@app.route('/health', methods=['GET'])
def health_check():
    ibge_ok = True
    try:
        r = requests.get('https://servicodados.ibge.gov.br/api/v1/localidades/estados', timeout=3)
        ibge_ok = (r.status_code == 200)
    except Exception:
        ibge_ok = False
    tray_ok = bool(TRAY_API_URL and TRAY_API_TOKEN)
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.now().isoformat(),
        'cds': len(CENTROS_DISTRIBUICAO),
        'ibge_api': 'disponível' if ibge_ok else 'indisponível',
        'tray_api': 'configurado' if tray_ok else 'não configurado',
        'versao': '2.0.0'
    })

@app.route('/', methods=['GET'])
def index():
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>API Multi-CD - Sistema de Frete Inteligente</title>
        <style>
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                margin: 0; padding: 0;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: #333;
            }}
            .container {{
                max-width: 900px; margin: 50px auto; background: white;
                border-radius: 20px; box-shadow: 0 20px 60px rgba(0,0,0,0.3); overflow: hidden;
            }}
            .header {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white; padding: 40px; text-align: center;
            }}
            .header h1 {{ margin: 0; font-size: 2.5em; }}
            .header p {{ margin: 10px 0 0 0; opacity: 0.9; }}
            .content {{ padding: 40px; }}
            .section {{ margin: 30px 0; }}
            .section h2 {{ color: #667eea; border-bottom: 3px solid #667eea; padding-bottom: 10px; }}
            .cds-grid {{
                display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                gap: 20px; margin: 20px 0;
            }}
            .cd-card {{ background: #f8f9fa; padding: 20px; border-radius: 10px; border-left: 4px solid #667eea; }}
            .cd-card h3 {{ margin-top: 0; color: #333; }}
            .cd-card p {{ margin: 5px 0; color: #666; }}
            .endpoint {{ background: #f1f3f4; padding: 15px; border-radius: 8px; margin: 15px 0; font-family: 'Courier New', monospace; }}
            .endpoint code {{ color: #d63384; }}
            .stats {{ display: flex; justify-content: space-around; margin: 30px 0; }}
            .stat {{ text-align: center; }}
            .stat-value {{ font-size: 3em; font-weight: bold; color: #667eea; }}
            .stat-label {{ color: #666; margin-top: 10px; }}
            .btn {{
                display: inline-block; padding: 12px 30px; background: #667eea; color: white;
                text-decoration: none; border-radius: 25px; margin: 10px; transition: all 0.3s;
            }}
            .btn:hover {{ background: #764ba2; transform: translateY(-2px); box-shadow: 0 5px 15px rgba(0,0,0,0.2); }}
            .footer {{ background: #f8f9fa; padding: 20px; text-align: center; color: #666; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🚚 API Multi-CD</h1>
                <p>Sistema Inteligente de Cálculo de Frete com 5 Centros de Distribuição</p>
            </div>
            <div class="content">
                <div class="stats">
                    <div class="stat">
                        <div class="stat-value">{len(CENTROS_DISTRIBUICAO)}</div>
                        <div class="stat-label">Centros de Distribuição</div>
                    </div>
                    <div class="stat">
                        <div class="stat-value">100%</div>
                        <div class="stat-label">Cobertura Brasil</div>
                    </div>
                    <div class="stat">
                        <div class="stat-value">API</div>
                        <div class="stat-label">IBGE Oficial</div>
                    </div>
                </div>
                <div class="section">
                    <h2>📍 Nossos Centros de Distribuição</h2>
                    <div class="cds-grid">
                        {''.join([f'''
                        <div class="cd-card">
                            <h3>{cd['nome']}</h3>
                            <p>📍 {cd['cidade']}/{cd['uf']}</p>
                            <p>📮 CEP: {cd['cep'][:5]}-{cd['cep'][5:]}</p>
                        </div>
                        ''' for cd in CENTROS_DISTRIBUICAO.values()])}
                    </div>
                </div>
                <div class="section">
                    <h2>🔌 Endpoints Disponíveis</h2>
                    <div class="endpoint">
                        <strong>POST/GET /frete</strong><br>
                        Calcula frete (compatível com Tray)<br>
                        <code>?cep_destino=90000000&prods=...</code>
                    </div>
                    <div class="endpoint">
                        <strong>GET /teste</strong><br>
                        Testa cálculo com interface visual<br>
                        <code>?cep=90000000&produto=PROD001</code>
                    </div>
                    <div class="endpoint">
                        <strong>GET /cds</strong><br>
                        Lista todos CDs disponíveis<br>
                        <code>Retorna JSON com informações dos CDs</code>
                    </div>
                    <div class="endpoint">
                        <strong>GET /health</strong><br>
                        Status da API e serviços<br>
                        <code>Health check e monitoramento</code>
                    </div>
                </div>
                <div class="section" style="text-align: center;">
                    <h2>🧪 Testar Agora</h2>
                    <a href="/teste?cep=90000000&produto=TESTE001" class="btn">Testar Porto Alegre/RS</a>
                    <a href="/teste?cep=88000000&produto=TESTE001" class="btn">Testar Florianópolis/SC</a>
                    <a href="/teste?cep=30000000&produto=TESTE001" class="btn">Testar Belo Horizonte/MG</a>
                    <a href="/cds" class="btn">Ver Todos CDs</a>
                    <a href="/health" class="btn">Status da API</a>
                </div>
                <div class="section">
                    <h2>✨ Funcionalidades</h2>
                    <ul>
                        <li>✅ Coordenadas via BrasilAPI (CEP v2), com fallback por capital</li>
                        <li>✅ Haversine + fator rodoviário</li>
                        <li>✅ Seleção automática do CD mais próximo</li>
                        <li>✅ Verificação de estoque via API Tray</li>
                        <li>✅ Cálculo de prazo e valor</li>
                        <li>✅ Compatível 100% com Tray</li>
                        <li>✅ Resposta em XML padrão Tray</li>
                    </ul>
                </div>
            </div>
            <div class="footer">
                <p>API Multi-CD v2.0.0 | Sistema de Frete Inteligente</p>
                <p>Desenvolvido para integração com Tray Commerce</p>
            </div>
        </div>
    </body>
    </html>
    """

# -----------------------------------------------------------------------------
# RUN (local)
# -----------------------------------------------------------------------------
if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    print("\n" + "="*70)
    print("🚀 INICIANDO API MULTI-CD")
    print("="*70)
    print(f"🌐 Porta: {port}")
    print(f"📦 CDs configurados: {len(CENTROS_DISTRIBUICAO)}")
    print(f"🔑 Token configurado: {'Sim' if TOKEN_SECRETO != 'teste123' else 'Não (usando padrão)'}")
    print(f"💰 Valor/km: R$ {DEFAULT_VALOR_KM:.2f}")
    print(f"🏪 Tray API: {'Configurada' if TRAY_API_URL else 'Não configurada'}")
    print("="*70 + "\n")
    app.run(host='0.0.0.0', port=port, debug=os.getenv('DEBUG', 'False').lower() == 'true')
