import streamlit as st
import pandas as pd
import folium
from folium.plugins import HeatMap, MarkerCluster
from streamlit_folium import st_folium
from io import BytesIO
import tempfile
import os

st.set_page_config(page_title="Mapa de Calor Geográfico", layout="wide")

st.title("Mapa de Calor Geográfico Interativo")

# =========================================================
# FUNÇÕES AUXILIARES
# =========================================================

def carregar_dados(uploaded_file):
    nome = uploaded_file.name.lower()

    if nome.endswith(".csv"):
        df = pd.read_csv(uploaded_file)
    elif nome.endswith(".xlsx") or nome.endswith(".xls"):
        df = pd.read_excel(uploaded_file)
    else:
        st.error("Formato não suportado. Carrega um ficheiro CSV ou Excel.")
        return None

    return df


def extrair_familia(natureza):
    if pd.isna(natureza):
        return None

    texto = str(natureza)
    partes = [p.strip() for p in texto.split("->")]

    # Exemplo:
    # 1501 -> Incêndio -> Equipamentos -> Contentores de lixo
    # queremos: Incêndio
    if len(partes) >= 2:
        return partes[1]

    return texto.strip()


def preparar_dados(df):
    df = df.copy()

    # Normalizar nomes das colunas (remove espaços laterais)
    df.columns = [c.strip() for c in df.columns]

    colunas_obrigatorias = ["Latitude", "Longitude", "Data", "Natureza"]
    em_falta = [c for c in colunas_obrigatorias if c not in df.columns]

    if em_falta:
        st.error(f"Faltam colunas obrigatórias: {', '.join(em_falta)}")
        return None

    # Converter data
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")

    # Remover registos inválidos para o mapa
    df = df.dropna(subset=["Latitude", "Longitude", "Data"])

    # Garantir tipo numérico das coordenadas
    df["Latitude"] = pd.to_numeric(df["Latitude"], errors="coerce")
    df["Longitude"] = pd.to_numeric(df["Longitude"], errors="coerce")
    df = df.dropna(subset=["Latitude", "Longitude"])

    # Nova coluna: Natureza_Familia
    df["Natureza_Familia"] = df["Natureza"].apply(extrair_familia)

    # Nova coluna: Ano
    df["Ano"] = df["Data"].dt.year

    return df


def criar_mapa(df_filtrado, raio=18, blur=12, gradiente=None, mostrar_marcadores=True):
    if df_filtrado.empty:
        return None

    centro_lat = df_filtrado["Latitude"].mean()
    centro_lon = df_filtrado["Longitude"].mean()

    mapa = folium.Map(location=[centro_lat, centro_lon], zoom_start=12, control_scale=True)

    # Heatmap
    heat_data = df_filtrado[["Latitude", "Longitude"]].values.tolist()

    HeatMap(
        heat_data,
        radius=raio,
        blur=blur,
        gradient=gradiente if gradiente else None
    ).add_to(mapa)

    # Marcadores com popup
    if mostrar_marcadores:
        cluster = MarkerCluster(name="Ocorrências").add_to(mapa)

        for _, row in df_filtrado.iterrows():
            popup_html = f"""
            <b>Ocorrência:</b> {row.get('Ocorrência', '')}<br>
            <b>Data:</b> {row['Data'].strftime('%d-%m-%Y') if pd.notnull(row['Data']) else ''}<br>
            <b>Família:</b> {row.get('Natureza_Familia', '')}<br>
            <b>Natureza:</b> {row.get('Natureza', '')}<br>
            <b>Morada:</b> {row.get('Morada', '')}<br>
            <b>Freguesia:</b> {row.get('Freguesia', '')}<br>
            <b>CBV:</b> {row.get('CBV', '')}
            """

            folium.Marker(
                location=[row["Latitude"], row["Longitude"]],
                popup=folium.Popup(popup_html, max_width=350),
                tooltip=row.get("Natureza_Familia", "Ocorrência")
            ).add_to(cluster)

    folium.LayerControl().add_to(mapa)
    return mapa


def exportar_mapa_html(mapa):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".html") as tmp:
        mapa.save(tmp.name)
        tmp.seek(0)
        with open(tmp.name, "rb") as f:
            html_bytes = f.read()
    return html_bytes


# =========================================================
# SIDEBAR - CARREGAMENTO
# =========================================================

st.sidebar.header("Carregamento de dados")
uploaded_file = st.sidebar.file_uploader(
    "Carregar ficheiro CSV ou Excel",
    type=["csv", "xlsx", "xls"]
)

if uploaded_file is None:
    st.info("Carrega um ficheiro para começar.")
    st.stop()

df = carregar_dados(uploaded_file)
if df is None:
    st.stop()

df = preparar_dados(df)
if df is None or df.empty:
    st.error("Não foi possível preparar os dados.")
    st.stop()

# =========================================================
# SIDEBAR - FILTROS
# =========================================================

st.sidebar.header("Filtros")

anos_disponiveis = sorted(df["Ano"].dropna().unique().tolist())
familias_disponiveis = sorted(df["Natureza_Familia"].dropna().unique().tolist())

freguesias_disponiveis = sorted(df["Freguesia"].dropna().unique().tolist()) if "Freguesia" in df.columns else []
cbv_disponiveis = sorted(df["CBV"].dropna().unique().tolist()) if "CBV" in df.columns else []

anos_sel = st.sidebar.multiselect(
    "Ano",
    options=anos_disponiveis,
    default=anos_disponiveis
)

familias_sel = st.sidebar.multiselect(
    "Natureza / Família",
    options=familias_disponiveis,
    default=familias_disponiveis
)

if "Freguesia" in df.columns:
    freguesias_sel = st.sidebar.multiselect(
        "Freguesia",
        options=freguesias_disponiveis,
        default=freguesias_disponiveis
    )
else:
    freguesias_sel = None

if "CBV" in df.columns:
    cbv_sel = st.sidebar.multiselect(
        "CBV",
        options=cbv_disponiveis,
        default=cbv_disponiveis
    )
else:
    cbv_sel = None

# =========================================================
# SIDEBAR - PARÂMETROS DO MAPA
# =========================================================

st.sidebar.header("Parâmetros do mapa")

raio = st.sidebar.slider("Raio do heatmap", min_value=5, max_value=40, value=18)
blur = st.sidebar.slider("Blur", min_value=5, max_value=30, value=12)
mostrar_marcadores = st.sidebar.checkbox("Mostrar marcadores com popup", value=True)

usar_gradiente = st.sidebar.checkbox("Usar gradiente personalizado", value=False)
gradiente = None

if usar_gradiente:
    gradiente = {
        0.2: "blue",
        0.4: "lime",
        0.6: "yellow",
        0.8: "orange",
        1.0: "red"
    }

# =========================================================
# APLICAR FILTROS
# =========================================================

df_filtrado = df.copy()

if anos_sel:
    df_filtrado = df_filtrado[df_filtrado["Ano"].isin(anos_sel)]

if familias_sel:
    df_filtrado = df_filtrado[df_filtrado["Natureza_Familia"].isin(familias_sel)]

if freguesias_sel is not None:
    df_filtrado = df_filtrado[df_filtrado["Freguesia"].isin(freguesias_sel)]

if cbv_sel is not None:
    df_filtrado = df_filtrado[df_filtrado["CBV"].isin(cbv_sel)]

# =========================================================
# RESUMO
# =========================================================

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total de registos", len(df_filtrado))
col2.metric("Anos selecionados", len(anos_sel))
col3.metric("Famílias selecionadas", len(familias_sel))
col4.metric("Famílias disponíveis", df_filtrado["Natureza_Familia"].nunique())

with st.expander("Pré-visualização dos dados filtrados"):
    st.dataframe(df_filtrado, use_container_width=True)

# =========================================================
# MAPA
# =========================================================

if df_filtrado.empty:
    st.warning("Não existem dados para os filtros selecionados.")
else:
    mapa = criar_mapa(
        df_filtrado,
        raio=raio,
        blur=blur,
        gradiente=gradiente,
        mostrar_marcadores=mostrar_marcadores
    )

    st.subheader("Mapa")
    st_folium(mapa, width=None, height=700)

    # Exportação HTML
    html_bytes = exportar_mapa_html(mapa)
    st.download_button(
        label="Exportar mapa para HTML",
        data=html_bytes,
        file_name="mapa_calor_filtrado.html",
        mime="text/html"
    )