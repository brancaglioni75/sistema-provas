# prova_web_streamlit.py

# prova_web_streamlit.py
# VERSÃO COMPLETA GOOGLE SHEETS

import streamlit as st
import pandas as pd
import random
import re
import hashlib
import secrets
import gspread

from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials

# =====================================================
# CONFIG
# =====================================================
st.set_page_config(
    page_title="Sistema de Provas",
    layout="wide"
)

TEMPO_LIMITE = 60 * 60
META_PERCENTUAL = 95.0

ABA_QUESTOES = "questoes"
ABA_ALUNOS = "alunos"
ABA_RESULTADOS = "resultados"

# =====================================================
# GOOGLE SHEETS
# =====================================================
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


def salvar_df(nome, df):
    ws = aba(nome)
    ws.clear()

    if df.empty:
        return

    valores = [df.columns.tolist()] + df.astype(str).values.tolist()
    ws.update(valores)


def append_linha(nome, linha):
    aba(nome).append_row(linha)


# =====================================================
# UTIL
# =====================================================
def hash_senha(senha):
    return hashlib.sha256(senha.encode()).hexdigest()


def limpar_numero(v):
    return re.sub(r"\D", "", str(v))


def validar_email(email):
    padrao = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
    return bool(re.match(padrao, str(email)))


def tempo_mmss(seg):
    seg = int(seg)
    m = seg // 60
    s = seg % 60
    return f"{m:02d}:{s:02d}"


def senha_temp():
    letras = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
    return "".join(secrets.choice(letras) for _ in range(8))


# =====================================================
# QUESTÕES
# =====================================================
def carregar_questoes():
    try:
        df = ler_df(ABA_QUESTOES)

        if df.empty:
            return []

        df.columns = [c.strip().lower() for c in df.columns]

        questoes = []

        colunas_opcoes = [c for c in df.columns if c.startswith("opcao_")]
        colunas_opcoes.sort()

        for _, row in df.iterrows():
            opcoes = []
            mapa = {}

            for col in colunas_opcoes:
                valor = row[col]

                if str(valor).strip():
                    letra = col.split("_")[-1].upper()
                    mapa[letra] = str(valor)
                    opcoes.append(str(valor))

            corretas = []

            for letra in str(row["correta"]).replace(" ", "").split(","):
                letra = letra.upper()
                if letra in mapa:
                    corretas.append(mapa[letra])

            questoes.append({
                "id": int(row["id"]),
                "materia": str(row["materia"]),
                "tipo": str(row["tipo"]).lower(),
                "pergunta": str(row["pergunta"]),
                "opcoes": opcoes,
                "corretas": corretas
            })

        return questoes

    except:
        return []


# =====================================================
# ALUNOS
# =====================================================
def carregar_alunos():
    df = ler_df(ABA_ALUNOS)

    if df.empty:
        return pd.DataFrame(columns=[
            "id_aluno",
            "nome",
            "cpf",
            "email",
            "senha_hash",
            "ativo",
            "data_cadastro",
            "troca_senha_pendente"
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

    cpf = limpar_numero(cpf)
    email = email.lower()

    if cpf in set(df["cpf"].astype(str)):
        return False, "CPF já cadastrado"

    if email in set(df["email"].astype(str)):
        return False, "E-mail já cadastrado"

    novo = pd.DataFrame([{
        "id_aluno": proximo_id(),
        "nome": nome,
        "cpf": cpf,
        "email": email,
        "senha_hash": hash_senha(senha),
        "ativo": True,
        "data_cadastro": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "troca_senha_pendente": False
    }])

    df = pd.concat([df, novo], ignore_index=True)
    salvar_alunos(df)

    return True, "Cadastro realizado"


def login_sistema(login, senha):
    df = carregar_alunos()

    if df.empty:
        return None

    login = login.lower()
    cpf = limpar_numero(login)

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


# =====================================================
# RESULTADOS
# =====================================================
def salvar_resultado(aluno, materia, resumo):
    linha = [
        aluno["id_aluno"],
        aluno["nome"],
        aluno["email"],
        materia,
        resumo["data_realizacao"],
        resumo["total_questoes"],
        resumo["acertos"],
        resumo["percentual"],
        resumo["nota"],
        resumo["tempo_segundos"],
        resumo["tempo"]
    ]

    append_linha(ABA_RESULTADOS, linha)


def carregar_resultados():
    df = ler_df(ABA_RESULTADOS)

    if df.empty:
        return df

    if "data_realizacao" in df.columns:
        df["data_realizacao"] = pd.to_datetime(
            df["data_realizacao"],
            errors="coerce"
        )

    return df


# =====================================================
# ESTADO
# =====================================================
if "usuario" not in st.session_state:
    st.session_state.usuario = None

if "prova_iniciada" not in st.session_state:
    st.session_state.prova_iniciada = False

if "inicio_prova" not in st.session_state:
    st.session_state.inicio_prova = None

if "questoes_prova" not in st.session_state:
    st.session_state.questoes_prova = []

# =====================================================
# TELA LOGIN
# =====================================================
st.title("🔵 Sistema de Provas Online")

if st.session_state.usuario is None:

    tab1, tab2, tab3 = st.tabs([
        "Login",
        "Cadastro",
        "Ranking"
    ])

    with tab1:
        st.subheader("Entrar")

        lg = st.text_input("CPF ou e-mail")
        pw = st.text_input("Senha", type="password")

        if st.button("Entrar"):
            u = login_sistema(lg, pw)

            if u:
                st.session_state.usuario = u
                st.rerun()
            else:
                st.error("Login inválido")

    with tab2:
        st.subheader("Novo cadastro")

        nome = st.text_input("Nome")
        cpf = st.text_input("CPF")
        email = st.text_input("E-mail")
        senha = st.text_input("Senha", type="password")

        if st.button("Cadastrar"):
            ok, msg = cadastrar(nome, cpf, email, senha)

            if ok:
                st.success(msg)
            else:
                st.error(msg)

    with tab3:
        st.subheader("Ranking Geral")

        df = carregar_resultados()

        if df.empty:
            st.info("Sem ranking")
        else:
            df = df.sort_values(
                by=["nota", "percentual"],
                ascending=False
            )

            st.dataframe(df, use_container_width=True)

# =====================================================
# ÁREA ALUNO
# =====================================================
else:
    aluno = st.session_state.usuario

    col1, col2 = st.columns([5, 1])

    with col1:
        st.success(f"Olá {aluno['nome']}")

    with col2:
        if st.button("Sair"):
            st.session_state.usuario = None
            st.rerun()

    abas = st.tabs([
        "Fazer prova",
        "Meu histórico",
        "Dashboard"
    ])

    # ===============================================
    # PROVA
    # ===============================================
    with abas[0]:
        questoes = carregar_questoes()

        materias = sorted(
            list(set(q["materia"] for q in questoes))
        )

        materia = st.selectbox(
            "Matéria",
            ["Todas"] + materias
        )

        if materia == "Todas":
            prova = questoes
        else:
            prova = [q for q in questoes if q["materia"] == materia]

        if st.button("Iniciar prova"):
            random.shuffle(prova)

            for q in prova:
                random.shuffle(q["opcoes"])

            st.session_state.questoes_prova = prova
            st.session_state.prova_iniciada = True
            st.session_state.inicio_prova = datetime.now()
            st.rerun()

        if st.session_state.prova_iniciada:

            decorrido = int(
                (datetime.now() -
                 st.session_state.inicio_prova).total_seconds()
            )

            restante = TEMPO_LIMITE - decorrido

            if restante < 0:
                restante = 0

            st.info(
                f"⏳ Tempo restante: {tempo_mmss(restante)}"
            )

            respostas = {}

            with st.form("form_prova"):

                for i, q in enumerate(
                    st.session_state.questoes_prova,
                    start=1
                ):
                    st.markdown(f"### Questão {i}")
                    st.write(q["pergunta"])

                    if q["tipo"] == "multipla":
                        respostas[str(q["id"])] = st.multiselect(
                            "Resposta",
                            q["opcoes"]
                        )
                    else:
                        respostas[str(q["id"])] = st.radio(
                            "Resposta",
                            q["opcoes"],
                            index=None
                        )

                fim = st.form_submit_button("Finalizar")

            if fim:

                total = len(st.session_state.questoes_prova)
                acertos = 0

                for q in st.session_state.questoes_prova:
                    marc = respostas[str(q["id"])]

                    if q["tipo"] == "multipla":
                        if set(marc) == set(q["corretas"]):
                            acertos += 1
                    else:
                        if marc == q["corretas"][0]:
                            acertos += 1

                tempo = int(
                    (datetime.now() -
                     st.session_state.inicio_prova).total_seconds()
                )

                perc = round(acertos / total * 100, 2)
                nota = round(acertos / total * 10, 2)

                resumo = {
                    "data_realizacao":
                        datetime.now().strftime(
                            "%Y-%m-%d %H:%M:%S"
                        ),
                    "total_questoes": total,
                    "acertos": acertos,
                    "percentual": perc,
                    "nota": nota,
                    "tempo_segundos": tempo,
                    "tempo": tempo_mmss(tempo)
                }

                salvar_resultado(
                    aluno,
                    materia,
                    resumo
                )

                st.success("Prova finalizada")

                st.metric("Nota", nota)
                st.metric("Percentual", f"{perc}%")
                st.metric("Tempo", tempo_mmss(tempo))

                st.session_state.prova_iniciada = False

    # ===============================================
    # HISTÓRICO
    # ===============================================
    with abas[1]:
        df = carregar_resultados()

        if df.empty:
            st.info("Sem histórico")
        else:
            df = df[
                pd.to_numeric(df["id_aluno"])
                ==
                int(aluno["id_aluno"])
            ]

            st.dataframe(df, use_container_width=True)

    # ===============================================
    # DASHBOARD
    # ===============================================
    with abas[2]:
        df = carregar_resultados()

        if df.empty:
            st.info("Sem dados")
        else:
            df = df[
                pd.to_numeric(df["id_aluno"])
                ==
                int(aluno["id_aluno"])
            ]

            if not df.empty:
                media = round(
                    pd.to_numeric(df["percentual"]).mean(),
                    2
                )

                melhor = round(
                    pd.to_numeric(df["percentual"]).max(),
                    2
                )

                meta = int(
                    (
                        pd.to_numeric(df["percentual"])
                        >= META_PERCENTUAL
                    ).sum()
                )

                c1, c2, c3 = st.columns(3)

                c1.metric("Média", f"{media}%")
                c2.metric("Melhor", f"{melhor}%")
                c3.metric("Meta 95%", meta)

                df["tentativa"] = range(1, len(df) + 1)

                chart = df.set_index("tentativa")[
                    ["percentual"]
                ]

                st.line_chart(chart)
