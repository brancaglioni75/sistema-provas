# ==========================================================
# prova_web_streamlit.py
# SISTEMA DE PROVAS ONLINE - GOOGLE SHEETS
# VERSÃO CORRIGIDA STREAMLIT CLOUD
# ==========================================================

import streamlit as st
import pandas as pd
import random
import hashlib
import re
import gspread
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials

# ==========================================================
# CONFIG
# ==========================================================
st.set_page_config(
    page_title="Sistema de Provas Online",
    layout="wide"
)

TEMPO_LIMITE = 60 * 60
META = 95

ABA_QUESTOES = "questoes"
ABA_ALUNOS = "alunos"
ABA_RESULTADOS = "resultados"

# ==========================================================
# GOOGLE SHEETS
# ==========================================================
@st.cache_resource
def conectar_google():

    creds = dict(st.secrets["gcp_service_account"])

    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]

    auth = ServiceAccountCredentials.from_json_keyfile_dict(
        creds,
        scope
    )

    cliente = gspread.authorize(auth)

    planilha = cliente.open_by_key(
        st.secrets["google_sheets"]["spreadsheet_key"]
    )

    return planilha


def aba(nome):
    return conectar_google().worksheet(nome)


def ler_df(nome):
    dados = aba(nome).get_all_records()
    return pd.DataFrame(dados)


def append(nome, linha):
    aba(nome).append_row(linha)


def salvar_df(nome, df):
    ws = aba(nome)
    ws.clear()

    if not df.empty:
        ws.update(
            [df.columns.tolist()] +
            df.astype(str).values.tolist()
        )


# ==========================================================
# UTIL
# ==========================================================
def hash_senha(txt):
    return hashlib.sha256(txt.encode()).hexdigest()


def limpar_num(v):
    return re.sub(r"\D", "", str(v))


def tempo(seg):
    seg = int(seg)
    m = seg // 60
    s = seg % 60
    return f"{m:02d}:{s:02d}"


# ==========================================================
# ALUNOS
# ==========================================================
def carregar_alunos():

    df = ler_df(ABA_ALUNOS)

    if df.empty:
        return pd.DataFrame(columns=[
            "id_aluno",
            "nome",
            "cpf",
            "email",
            "senha_hash",
            "ativo"
        ])

    return df


def salvar_alunos(df):
    salvar_df(ABA_ALUNOS, df)


def proximo_id():

    df = carregar_alunos()

    if df.empty:
        return 1

    return int(pd.to_numeric(df["id_aluno"]).max()) + 1


def cadastrar(nome, cpf, email, senha):

    df = carregar_alunos()

    cpf = limpar_num(cpf)
    email = email.lower()

    if cpf in set(df["cpf"].astype(str)):
        return False

    if email in set(df["email"].astype(str)):
        return False

    novo = pd.DataFrame([{
        "id_aluno": proximo_id(),
        "nome": nome,
        "cpf": cpf,
        "email": email,
        "senha_hash": hash_senha(senha),
        "ativo": True
    }])

    df = pd.concat([df, novo], ignore_index=True)

    salvar_alunos(df)

    return True


def login(login, senha):

    df = carregar_alunos()

    login = login.lower()
    cpf = limpar_num(login)

    filtro = (
        (df["email"].astype(str).str.lower() == login)
        |
        (df["cpf"].astype(str) == cpf)
    )

    x = df[filtro]

    if x.empty:
        return None

    user = x.iloc[0].to_dict()

    if user["senha_hash"] == hash_senha(senha):
        return user

    return None


# ==========================================================
# QUESTÕES
# ==========================================================
def carregar_questoes():

    df = ler_df(ABA_QUESTOES)

    if df.empty:
        return []

    questoes = []

    for _, row in df.iterrows():

        opcoes = []

        for c in df.columns:
            if c.startswith("opcao_"):
                if str(row[c]).strip():
                    opcoes.append(str(row[c]))

        corretas = []

        letras = str(row["correta"]).split(",")

        for letra in letras:
            letra = letra.strip().upper()

            col = f"opcao_{letra.lower()}"

            if col in row:
                corretas.append(str(row[col]))

        questoes.append({
            "id": row["id"],
            "materia": row["materia"],
            "tipo": row["tipo"],
            "pergunta": row["pergunta"],
            "opcoes": opcoes,
            "corretas": corretas
        })

    return questoes


# ==========================================================
# RESULTADOS
# ==========================================================
def salvar_resultado(user, materia, total, acertos, tempo_seg):

    perc = round(acertos / total * 100, 2)
    nota = round(acertos / total * 10, 2)

    append(ABA_RESULTADOS, [
        user["id_aluno"],
        user["nome"],
        user["email"],
        materia,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        total,
        acertos,
        perc,
        nota,
        tempo_seg,
        tempo(tempo_seg)
    ])


def carregar_resultados():
    return ler_df(ABA_RESULTADOS)


# ==========================================================
# SESSION
# ==========================================================
if "user" not in st.session_state:
    st.session_state.user = None

if "iniciada" not in st.session_state:
    st.session_state.iniciada = False

if "inicio" not in st.session_state:
    st.session_state.inicio = None

if "prova" not in st.session_state:
    st.session_state.prova = []


# ==========================================================
# VISUAL
# ==========================================================
st.markdown("""
<style>
h1,h2,h3{
color:#0d47a1;
}
.stButton>button{
background:#1565c0;
color:white;
border-radius:8px;
}
</style>
""", unsafe_allow_html=True)

st.title("🔵 Sistema de Provas Online")


# ==========================================================
# LOGIN
# ==========================================================
if st.session_state.user is None:

    tab1, tab2, tab3 = st.tabs([
        "Login",
        "Cadastro",
        "Ranking público"
    ])

    # LOGIN
    with tab1:

        st.subheader("Entrar")

        lg = st.text_input("CPF ou e-mail")
        pw = st.text_input("Senha")

        if st.button("Entrar"):

            u = login(lg, pw)

            if u:
                st.session_state.user = u
                st.rerun()
            else:
                st.error("Login inválido")

    # CADASTRO
    with tab2:

        st.subheader("Novo cadastro")

        nome = st.text_input("Nome completo")
        cpf = st.text_input("CPF")
        email = st.text_input("E-mail")
        senha = st.text_input("Criar senha")

        if st.button("Cadastrar"):

            ok = cadastrar(
                nome,
                cpf,
                email,
                senha
            )

            if ok:
                st.success("Cadastro realizado")
            else:
                st.error("CPF ou e-mail já cadastrado")

    # RANKING
    with tab3:

        st.subheader("Ranking Geral")

        df = carregar_resultados()

        if not df.empty:

            df = df.sort_values(
                by="nota",
                ascending=False
            )

            st.dataframe(
                df[[
                    "nome",
                    "materia",
                    "percentual",
                    "nota"
                ]],
                use_container_width=True
            )

# ==========================================================
# ÁREA INTERNA
# ==========================================================
else:

    user = st.session_state.user

    c1, c2 = st.columns([5, 1])

    c1.success(f"Olá, {user['nome']} 👋")

    if c2.button("Sair"):
        st.session_state.user = None
        st.rerun()

    abas = st.tabs([
        "Fazer prova",
        "Meu histórico",
        "Dashboard"
    ])

    # ======================================================
    # PROVA
    # ======================================================
    with abas[0]:

        questoes = carregar_questoes()

        materias = sorted(
            list(set(
                q["materia"]
                for q in questoes
            ))
        )

        materia = st.selectbox(
            "Matéria",
            ["Todas"] + materias
        )

        if materia == "Todas":
            prova = questoes
        else:
            prova = [
                q for q in questoes
                if q["materia"] == materia
            ]

        if st.button("Iniciar prova"):

            random.shuffle(prova)

            for q in prova:
                random.shuffle(q["opcoes"])

            st.session_state.prova = prova
            st.session_state.iniciada = True
            st.session_state.inicio = datetime.now()

            st.rerun()

        if st.session_state.iniciada:

            decorrido = int(
                (
                    datetime.now() -
                    st.session_state.inicio
                ).total_seconds()
            )

            restante = TEMPO_LIMITE - decorrido

            if restante < 0:
                restante = 0

            st.info(
                f"⏳ Tempo restante: {tempo(restante)}"
            )

            respostas = {}

            with st.form("formulario"):

                for i, q in enumerate(
                    st.session_state.prova,
                    start=1
                ):

                    st.markdown(
                        f"### Questão {i}"
                    )

                    st.write(q["pergunta"])

                    if q["tipo"] == "multipla":

                        respostas[q["id"]] = st.multiselect(
                            "Resposta",
                            q["opcoes"]
                        )

                    else:

                        respostas[q["id"]] = st.radio(
                            "Resposta",
                            q["opcoes"],
                            index=None
                        )

                fim = st.form_submit_button(
                    "Finalizar prova"
                )

            if fim:

                acertos = 0
                total = len(
                    st.session_state.prova
                )

                for q in st.session_state.prova:

                    marc = respostas[q["id"]]

                    if q["tipo"] == "multipla":

                        if set(marc) == set(q["corretas"]):
                            acertos += 1

                    else:

                        if marc == q["corretas"][0]:
                            acertos += 1

                tempo_seg = int(
                    (
                        datetime.now() -
                        st.session_state.inicio
                    ).total_seconds()
                )

                salvar_resultado(
                    user,
                    materia,
                    total,
                    acertos,
                    tempo_seg
                )

                st.success("Prova finalizada")

                st.session_state.iniciada = False

    # ======================================================
    # HISTÓRICO
    # ======================================================
    with abas[1]:

        df = carregar_resultados()

        if not df.empty:

            df = df[
                pd.to_numeric(df["id_aluno"])
                ==
                int(user["id_aluno"])
            ]

            st.dataframe(
                df,
                use_container_width=True
            )

    # ======================================================
    # DASHBOARD
    # ======================================================
    with abas[2]:

        df = carregar_resultados()

        if not df.empty:

            df = df[
                pd.to_numeric(df["id_aluno"])
                ==
                int(user["id_aluno"])
            ]

            if not df.empty:

                media = round(
                    pd.to_numeric(
                        df["percentual"]
                    ).mean(),
                    2
                )

                melhor = round(
                    pd.to_numeric(
                        df["percentual"]
                    ).max(),
                    2
                )

                meta = int(
                    (
                        pd.to_numeric(
                            df["percentual"]
                        ) >= META
                    ).sum()
                )

                a, b, c = st.columns(3)

                a.metric(
                    "Média",
                    f"{media}%"
                )

                b.metric(
                    "Melhor",
                    f"{melhor}%"
                )

                c.metric(
                    "Meta 95%",
                    meta
                )

                df["tentativa"] = range(
                    1,
                    len(df) + 1
                )

                st.line_chart(
                    df.set_index("tentativa")[
                        ["percentual"]
                    ]
                )
