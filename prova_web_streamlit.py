# ==========================================================
# prova_web_streamlit.py
# SISTEMA DE PROVAS ONLINE - GOOGLE SHEETS
# VERSÃO CORRIGIDA STREAMLIT CLOUD
# ==========================================================

# prova_web_streamlit.py
# Sistema de Provas Online
# Tudo em Google Sheets: questoes, alunos, resultados

import streamlit as st
import pandas as pd
import random
import re
import secrets
import hashlib
from datetime import datetime
from io import BytesIO

import gspread
from oauth2client.service_account import ServiceAccountCredentials

# =========================================================
# CONFIGURAÇÕES
# =========================================================
st.set_page_config(page_title="Sistema de Provas", layout="wide")

TEMPO_LIMITE = 60 * 60  # 60 minutos
META_PERCENTUAL = 95.0

ABA_QUESTOES = "questoes"
ABA_ALUNOS = "alunos"
ABA_RESULTADOS = "resultados"

# =========================================================
# GOOGLE SHEETS
# =========================================================
@st.cache_resource
def conectar_gsheets():
    creds = dict(st.secrets["gcp_service_account"])
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    auth = ServiceAccountCredentials.from_json_keyfile_dict(creds, scope)
    cliente = gspread.authorize(auth)
    return cliente.open_by_key(st.secrets["google_sheets"]["spreadsheet_key"])


def obter_aba(nome_aba: str):
    return conectar_gsheets().worksheet(nome_aba)


def ler_df(nome_aba: str) -> pd.DataFrame:
    dados = obter_aba(nome_aba).get_all_records()
    return pd.DataFrame(dados)


def salvar_df(nome_aba: str, df: pd.DataFrame):
    ws = obter_aba(nome_aba)
    ws.clear()

    if df.empty:
        return

    df = df.fillna("")
    valores = [df.columns.tolist()] + df.astype(str).values.tolist()
    ws.update(valores)


def append_linha(nome_aba: str, linha: list):
    obter_aba(nome_aba).append_row(linha, value_input_option="USER_ENTERED")


# =========================================================
# ESTILO
# =========================================================
st.markdown(
    """
    <style>
    h1,h2,h3 {
        color: #0d47a1;
    }
    .stButton > button {
        background: #1565c0;
        color: white;
        border-radius: 8px;
        border: none;
    }
    .stButton > button:hover {
        background: #0d47a1;
        color: white;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# =========================================================
# UTILITÁRIOS
# =========================================================
def hash_senha(senha: str) -> str:
    return hashlib.sha256(senha.encode("utf-8")).hexdigest()


def verificar_senha(senha_digitada: str, senha_hash: str) -> bool:
    return hash_senha(senha_digitada) == str(senha_hash)


def gerar_senha_temporaria(tamanho: int = 8) -> str:
    alfabeto = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
    return "".join(secrets.choice(alfabeto) for _ in range(tamanho))


def limpar_apenas_numeros(valor: str) -> str:
    return re.sub(r"\D", "", str(valor or ""))


def validar_email(email: str) -> bool:
    padrao = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
    return bool(re.match(padrao, str(email).strip()))


def validar_cpf(cpf: str) -> bool:
    cpf = limpar_apenas_numeros(cpf)

    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False

    soma1 = sum(int(cpf[i]) * (10 - i) for i in range(9))
    dig1 = (soma1 * 10) % 11
    dig1 = 0 if dig1 == 10 else dig1
    if dig1 != int(cpf[9]):
        return False

    soma2 = sum(int(cpf[i]) * (11 - i) for i in range(10))
    dig2 = (soma2 * 10) % 11
    dig2 = 0 if dig2 == 10 else dig2
    if dig2 != int(cpf[10]):
        return False

    return True


def mascarar_cpf(cpf: str) -> str:
    cpf = limpar_apenas_numeros(cpf)
    if len(cpf) != 11:
        return cpf
    return f"***.***.***-{cpf[9:]}"


def formatar_tempo_mmss(total_segundos) -> str:
    try:
        total_segundos = int(float(total_segundos))
    except Exception:
        return "00:00"

    minutos = total_segundos // 60
    segundos = total_segundos % 60
    return f"{minutos:02d}:{segundos:02d}"


def normalizar_bool_coluna(coluna: pd.Series, default=False) -> pd.Series:
    if coluna is None:
        return pd.Series(dtype=bool)

    return (
        coluna.fillna(default)
        .astype(str)
        .str.strip()
        .str.lower()
        .isin(["true", "1", "sim", "yes"])
    )


# =========================================================
# QUESTÕES
# =========================================================
def carregar_questoes():
    try:
        df = ler_df(ABA_QUESTOES)

        if df.empty:
            return []

        df.columns = [str(c).strip().lower() for c in df.columns]

        obrigatorias = {"id", "materia", "tipo", "pergunta", "correta"}
        if not obrigatorias.issubset(set(df.columns)):
            st.error("A aba 'questoes' não possui todas as colunas obrigatórias.")
            return []

        colunas_opcoes = [c for c in df.columns if c.startswith("opcao_")]
        colunas_opcoes.sort()

        questoes = []

        for _, row in df.iterrows():
            opcoes = []
            mapa_opcoes = {}

            for col in colunas_opcoes:
                valor = row.get(col)
                if pd.notna(valor) and str(valor).strip():
                    letra = col.split("_")[-1].upper()
                    texto = str(valor).strip()
                    mapa_opcoes[letra] = texto
                    opcoes.append({"letra": letra, "texto": texto})

            correta_bruta = str(row["correta"]).replace(" ", "").upper()
            letras_corretas = [x for x in correta_bruta.split(",") if x]
            textos_corretos = [mapa_opcoes[l] for l in letras_corretas if l in mapa_opcoes]

            try:
                qid = int(float(row["id"]))
            except Exception:
                continue

            questoes.append(
                {
                    "id": qid,
                    "materia": str(row["materia"]).strip(),
                    "tipo": str(row["tipo"]).strip().lower(),
                    "pergunta": str(row["pergunta"]).strip(),
                    "opcoes": opcoes,
                    "corretas": textos_corretos,
                }
            )

        return questoes

    except Exception as e:
        st.error(f"Erro ao carregar questões do Google Sheets: {e}")
        return []


# =========================================================
# ALUNOS
# =========================================================
def carregar_alunos() -> pd.DataFrame:
    try:
        df = ler_df(ABA_ALUNOS)
    except Exception:
        df = pd.DataFrame()

    colunas = [
        "id_aluno",
        "nome",
        "cpf",
        "email",
        "senha_hash",
        "ativo",
        "data_cadastro",
        "troca_senha_pendente",
    ]

    if df.empty:
        return pd.DataFrame(columns=colunas)

    for c in colunas:
        if c not in df.columns:
            if c in ["ativo", "troca_senha_pendente"]:
                df[c] = False
            else:
                df[c] = ""

    df["id_aluno"] = pd.to_numeric(df["id_aluno"], errors="coerce")
    df["nome"] = df["nome"].fillna("").astype(str).str.strip()
    df["cpf"] = df["cpf"].fillna("").astype(str).apply(limpar_apenas_numeros)
    df["email"] = df["email"].fillna("").astype(str).str.strip().str.lower()
    df["senha_hash"] = df["senha_hash"].fillna("").astype(str)
    df["ativo"] = normalizar_bool_coluna(df["ativo"], default=True)
    df["troca_senha_pendente"] = normalizar_bool_coluna(
        df["troca_senha_pendente"], default=False
    )
    df["data_cadastro"] = df["data_cadastro"].fillna("").astype(str)

    return df


def salvar_alunos(df: pd.DataFrame):
    salvar_df(ABA_ALUNOS, df)


def proximo_id_aluno(df: pd.DataFrame) -> int:
    if df.empty or "id_aluno" not in df.columns:
        return 1
    ids = pd.to_numeric(df["id_aluno"], errors="coerce").dropna()
    return int(ids.max()) + 1 if not ids.empty else 1


def cadastrar_aluno(nome: str, cpf: str, email: str, senha: str):
    nome = str(nome).strip()
    cpf = limpar_apenas_numeros(cpf)
    email = str(email).strip().lower()
    senha = str(senha)

    if not nome:
        return False, "Informe o nome completo."
    if not validar_cpf(cpf):
        return False, "CPF inválido."
    if not validar_email(email):
        return False, "E-mail inválido."
    if len(senha) < 6:
        return False, "A senha deve ter pelo menos 6 caracteres."

    alunos = carregar_alunos()

    if not alunos.empty and cpf in set(alunos["cpf"].astype(str)):
        return False, "CPF já cadastrado."
    if not alunos.empty and email in set(alunos["email"].astype(str)):
        return False, "E-mail já cadastrado."

    novo = pd.DataFrame(
        [
            {
                "id_aluno": proximo_id_aluno(alunos),
                "nome": nome,
                "cpf": cpf,
                "email": email,
                "senha_hash": hash_senha(senha),
                "ativo": True,
                "data_cadastro": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "troca_senha_pendente": False,
            }
        ]
    )

    alunos = pd.concat([alunos, novo], ignore_index=True)
    salvar_alunos(alunos)

    return True, f"Aluno cadastrado com sucesso. ID: {int(novo.iloc[0]['id_aluno'])}"


def autenticar_login(login: str, senha: str):
    login = str(login).strip().lower()
    alunos = carregar_alunos()

    if alunos.empty:
        return None

    login_cpf = limpar_apenas_numeros(login)

    filtro = (
        (alunos["email"].astype(str).str.lower() == login)
        | (alunos["cpf"].astype(str) == login_cpf)
    ) & (alunos["ativo"] == True)

    encontrados = alunos[filtro]

    if encontrados.empty:
        return None

    aluno = encontrados.iloc[0].to_dict()
    if verificar_senha(senha, aluno["senha_hash"]):
        return aluno
    return None


def redefinir_senha_imediata(identificador: str):
    identificador = str(identificador).strip().lower()
    alunos = carregar_alunos()

    if alunos.empty:
        return False, "Nenhum aluno cadastrado.", None

    identificador_cpf = limpar_apenas_numeros(identificador)

    filtro = (
        (alunos["email"].astype(str).str.strip().str.lower() == identificador)
        | (alunos["cpf"].astype(str).apply(limpar_apenas_numeros) == identificador_cpf)
    ) & (alunos["ativo"] == True)

    encontrados = alunos[filtro]

    if encontrados.empty:
        return False, "Aluno não encontrado pelo e-mail ou CPF informado.", None

    idx = encontrados.index[0]
    senha_temp = gerar_senha_temporaria()

    alunos.loc[idx, "senha_hash"] = hash_senha(senha_temp)
    alunos.loc[idx, "troca_senha_pendente"] = True
    salvar_alunos(alunos)

    return True, "Senha temporária gerada com sucesso.", senha_temp


def alterar_senha_usuario(id_aluno, senha_atual: str, nova_senha: str):
    alunos = carregar_alunos()
    encontrados = alunos[pd.to_numeric(alunos["id_aluno"], errors="coerce") == int(id_aluno)]

    if encontrados.empty:
        return False, "Usuário não encontrado."

    idx = encontrados.index[0]
    senha_hash = str(alunos.loc[idx, "senha_hash"])

    if not verificar_senha(senha_atual, senha_hash):
        return False, "Senha atual incorreta."

    if len(str(nova_senha)) < 6:
        return False, "A nova senha deve ter pelo menos 6 caracteres."

    alunos.loc[idx, "senha_hash"] = hash_senha(nova_senha)
    alunos.loc[idx, "troca_senha_pendente"] = False
    salvar_alunos(alunos)
    return True, "Senha alterada com sucesso."


def inativar_aluno(id_aluno):
    alunos = carregar_alunos()
    encontrados = alunos[pd.to_numeric(alunos["id_aluno"], errors="coerce") == int(id_aluno)]

    if encontrados.empty:
        return False, "Aluno não encontrado."

    idx = encontrados.index[0]
    alunos.loc[idx, "ativo"] = False
    salvar_alunos(alunos)
    return True, "Cadastro inativado com sucesso."


def reativar_aluno(id_aluno):
    alunos = carregar_alunos()
    encontrados = alunos[pd.to_numeric(alunos["id_aluno"], errors="coerce") == int(id_aluno)]

    if encontrados.empty:
        return False, "Aluno não encontrado."

    idx = encontrados.index[0]
    alunos.loc[idx, "ativo"] = True
    salvar_alunos(alunos)
    return True, "Cadastro reativado com sucesso."


def excluir_aluno(id_aluno):
    alunos = carregar_alunos()
    filtro = pd.to_numeric(alunos["id_aluno"], errors="coerce") == int(id_aluno)

    if not filtro.any():
        return False, "Aluno não encontrado."

    alunos = alunos[~filtro].reset_index(drop=True)
    salvar_alunos(alunos)
    return True, "Cadastro excluído com sucesso."


def atualizar_email_aluno(id_aluno, novo_email: str):
    novo_email = str(novo_email).strip().lower()

    if not validar_email(novo_email):
        return False, "E-mail inválido."

    alunos = carregar_alunos()
    filtro = pd.to_numeric(alunos["id_aluno"], errors="coerce") == int(id_aluno)

    if not filtro.any():
        return False, "Aluno não encontrado."

    conflito = alunos[
        (alunos["email"].astype(str).str.strip().str.lower() == novo_email)
        & (pd.to_numeric(alunos["id_aluno"], errors="coerce") != int(id_aluno))
    ]
    if not conflito.empty:
        return False, "Este e-mail já está cadastrado para outro aluno."

    idx = alunos[filtro].index[0]
    alunos.loc[idx, "email"] = novo_email
    salvar_alunos(alunos)
    return True, "E-mail atualizado com sucesso."


# =========================================================
# RESULTADOS
# =========================================================
def carregar_historico() -> pd.DataFrame:
    try:
        df = ler_df(ABA_RESULTADOS)
    except Exception:
        df = pd.DataFrame()

    if df.empty:
        return pd.DataFrame(
            columns=[
                "id_aluno",
                "nome",
                "email",
                "materia",
                "data_realizacao",
                "total_questoes",
                "acertos",
                "percentual",
                "nota",
                "tempo_segundos",
                "tempo",
            ]
        )

    if "id_aluno" not in df.columns:
        df["id_aluno"] = pd.NA

    if "data_realizacao" in df.columns:
        df["data_realizacao"] = pd.to_datetime(df["data_realizacao"], errors="coerce")

    if "tempo_segundos" in df.columns:
        df["tempo_segundos"] = pd.to_numeric(df["tempo_segundos"], errors="coerce")

    if "percentual" in df.columns:
        df["percentual"] = pd.to_numeric(df["percentual"], errors="coerce")

    if "nota" in df.columns:
        df["nota"] = pd.to_numeric(df["nota"], errors="coerce")

    if "tempo" not in df.columns and "tempo_segundos" in df.columns:
        df["tempo"] = df["tempo_segundos"].apply(
            lambda x: formatar_tempo_mmss(x) if pd.notna(x) else "00:00"
        )

    return df


def salvar_resultado(aluno, materia, resumo: dict):
    linha = [
        int(aluno["id_aluno"]),
        aluno["nome"],
        aluno["email"],
        materia,
        resumo["data_realizacao"],
        resumo["total_questoes"],
        resumo["acertos"],
        resumo["percentual"],
        resumo["nota"],
        resumo["tempo_segundos"],
        resumo["tempo"],
    ]
    append_linha(ABA_RESULTADOS, linha)


def excluir_tentativa(indice_real):
    historico = carregar_historico()

    if historico.empty:
        return

    historico = historico.drop(index=indice_real).reset_index(drop=True)
    salvar_df(ABA_RESULTADOS, historico)


def preparar_historico_aluno(historico, id_aluno, nome_aluno=None, email_aluno=None):
    if historico.empty:
        return historico.copy()

    historico = historico.copy()

    if "id_aluno" in historico.columns:
        filtrado = historico[
            pd.to_numeric(historico["id_aluno"], errors="coerce") == int(id_aluno)
        ].copy()
        if not filtrado.empty:
            return filtrado

    if nome_aluno and "nome" in historico.columns:
        hist = historico[
            historico["nome"].astype(str).str.strip().str.lower()
            == str(nome_aluno).strip().lower()
        ].copy()
        if not hist.empty:
            return hist

    if email_aluno and "email" in historico.columns:
        hist = historico[
            historico["email"].astype(str).str.strip().str.lower()
            == str(email_aluno).strip().lower()
        ].copy()
        if not hist.empty:
            return hist

    return historico.iloc[0:0].copy()


def obter_respostas_erradas(detalhes):
    if not detalhes:
        return pd.DataFrame()
    df = pd.DataFrame(detalhes)
    return df[df["acertou"] == "Não"].copy()


# =========================================================
# PROVA
# =========================================================
def limpar_respostas_da_tentativa():
    tentativa_id = st.session_state.get("tentativa_id")
    if not tentativa_id:
        return
    prefixo = f"q_{tentativa_id}_"
    for chave in list(st.session_state.keys()):
        if str(chave).startswith(prefixo):
            del st.session_state[chave]


def inicializar_prova(questoes_filtradas):
    limpar_respostas_da_tentativa()
    tentativa_id = datetime.now().strftime("%Y%m%d%H%M%S%f")

    prova = []
    for q in questoes_filtradas:
        item = q.copy()
        opcoes_embaralhadas = q["opcoes"][:]
        random.shuffle(opcoes_embaralhadas)
        item["opcoes_embaralhadas"] = opcoes_embaralhadas
        prova.append(item)

    random.shuffle(prova)

    st.session_state.tentativa_id = tentativa_id
    st.session_state.questoes_prova = prova
    st.session_state.prova_iniciada = True
    st.session_state.prova_finalizada = False
    st.session_state.inicio_prova = datetime.now()
    st.session_state.ultimo_resumo = None
    st.session_state.ultimos_detalhes = None
    st.session_state.tempo_esgotado = False
    st.rerun()


def corrigir_prova(respostas):
    total = len(st.session_state.questoes_prova)
    acertos = 0
    detalhes = []

    for q in st.session_state.questoes_prova:
        chave = str(q["id"])
        corretas = q["corretas"]

        if q["tipo"] == "multipla":
            marcadas = respostas.get(chave, [])
            acertou = set(marcadas) == set(corretas)
            resposta_usuario = ", ".join(marcadas) if marcadas else ""
        else:
            marcada = respostas.get(chave)
            acertou = marcada == corretas[0] if corretas else False
            resposta_usuario = marcada if marcada else ""

        if acertou:
            acertos += 1

        detalhes.append(
            {
                "questao_id": q["id"],
                "materia": q["materia"],
                "pergunta": q["pergunta"],
                "resposta_usuario": resposta_usuario,
                "resposta_correta": ", ".join(corretas),
                "acertou": "Sim" if acertou else "Não",
            }
        )

    fim = datetime.now()
    tempo_segundos = int((fim - st.session_state.inicio_prova).total_seconds())
    percentual = round((acertos / total) * 100, 2) if total else 0
    nota = round((acertos / total) * 10, 2) if total else 0

    resumo = {
        "data_realizacao": fim.strftime("%Y-%m-%d %H:%M:%S"),
        "total_questoes": total,
        "acertos": acertos,
        "percentual": percentual,
        "nota": nota,
        "tempo_segundos": tempo_segundos,
        "tempo": formatar_tempo_mmss(tempo_segundos),
    }

    return resumo, detalhes


# =========================================================
# DASHBOARD
# =========================================================
def exibir_dashboard_evolucao(historico_aluno):
    st.subheader("📊 Meu Dashboard")

    if historico_aluno.empty:
        st.info("Faça provas para visualizar sua evolução.")
        return

    historico_ordenado = historico_aluno.sort_values("data_realizacao", na_position="last").reset_index(drop=True)

    historico_ordenado["percentual"] = pd.to_numeric(
        historico_ordenado["percentual"], errors="coerce"
    ).fillna(0)

    historico_ordenado["nota"] = pd.to_numeric(
        historico_ordenado["nota"], errors="coerce"
    ).fillna(0)

    total_provas = len(historico_ordenado)
    percentual_medio = round(historico_ordenado["percentual"].mean(), 2)
    melhor_percentual = round(historico_ordenado["percentual"].max(), 2)
    provas_na_meta = int((historico_ordenado["percentual"] >= META_PERCENTUAL).sum())

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total de provas", total_provas)
    c2.metric("Média geral", f"{percentual_medio:.2f}%")
    c3.metric("Melhor resultado", f"{melhor_percentual:.2f}%")
    c4.metric("Meta 95%", provas_na_meta)

    st.markdown("---")

    historico_ordenado["Tentativa"] = range(1, len(historico_ordenado) + 1)
    graf = historico_ordenado[["Tentativa", "percentual"]].set_index("Tentativa")
    st.line_chart(graf)
    st.caption("Evolução do percentual por prova")

    tabela = historico_ordenado.copy()
    tabela["Meta atingida"] = tabela["percentual"].apply(lambda x: "Sim" if x >= 95 else "Não")

    if "data_realizacao" in tabela.columns:
        tabela["data_realizacao"] = tabela["data_realizacao"].dt.strftime("%d/%m/%Y %H:%M")

    colunas = [
        c
        for c in [
            "data_realizacao",
            "materia",
            "percentual",
            "nota",
            "tempo",
            "Meta atingida",
        ]
        if c in tabela.columns
    ]

    st.dataframe(tabela[colunas], use_container_width=True)


# =========================================================
# ESTADO
# =========================================================
if "usuario_logado" not in st.session_state:
    st.session_state.usuario_logado = None

if "prova_iniciada" not in st.session_state:
    st.session_state.prova_iniciada = False

if "prova_finalizada" not in st.session_state:
    st.session_state.prova_finalizada = False

if "tempo_esgotado" not in st.session_state:
    st.session_state.tempo_esgotado = False


# =========================================================
# INTERFACE
# =========================================================
st.title("🔵 Sistema de Provas Online")

if not st.session_state.usuario_logado:
    st.markdown("### Acesso ao sistema")
    st.caption("Entre com seu CPF ou e-mail para acessar sua área privada. O ranking geral continua disponível para consulta.")

    tab_login, tab_cadastro, tab_ranking_publico = st.tabs(
        ["Login", "Cadastro", "Ranking público"]
    )

    # =====================================================
    # LOGIN
    # =====================================================
    with tab_login:
        st.subheader("Entrar")

        with st.form("form_login", clear_on_submit=True):
            login = st.text_input("CPF ou e-mail")
            senha = st.text_input("Senha")
            entrar = st.form_submit_button("Entrar", use_container_width=True)

        if entrar:
            aluno = autenticar_login(login, senha)
            if aluno:
                st.session_state.usuario_logado = aluno
                st.success(f"Bem-vindo, {aluno['nome']}!")
                st.rerun()
            else:
                st.error("Login ou senha inválidos.")

        with st.expander("Esqueci minha senha"):
            st.caption("Informe seu e-mail ou CPF exatamente como no cadastro.")
            with st.form("form_esqueci_senha", clear_on_submit=True):
                identificador_recuperacao = st.text_input("Digite seu e-mail ou CPF")
                gerar_nova_senha = st.form_submit_button(
                    "Gerar senha temporária", use_container_width=True
                )

            if gerar_nova_senha:
                ok, msg, senha_temp = redefinir_senha_imediata(identificador_recuperacao)
                if ok:
                    st.success(msg)
                    st.warning(f"Sua senha temporária é: {senha_temp}")
                    st.info("Entre com essa senha e altere depois em 'Alterar minha senha'.")
                else:
                    st.error(msg)

    # =====================================================
    # CADASTRO
    # =====================================================
    with tab_cadastro:
        st.subheader("Cadastrar novo aluno")

        with st.form("form_cadastro", clear_on_submit=True):
            nome = st.text_input("Nome completo")
            cpf = st.text_input("CPF")
            email = st.text_input("E-mail")
            senha_cadastro = st.text_input("Crie uma senha")
            cadastrar = st.form_submit_button("Cadastrar", use_container_width=True)

        if cadastrar:
            ok, msg = cadastrar_aluno(nome, cpf, email, senha_cadastro)
            if ok:
                st.success(msg)
            else:
                st.error(msg)

        alunos = carregar_alunos()

        if not alunos.empty:
            exibicao = alunos.copy()
            exibicao["cpf"] = exibicao["cpf"].apply(mascarar_cpf)
            exibicao["status"] = exibicao["ativo"].apply(lambda x: "Ativo" if bool(x) else "Inativo")

            colunas = [
                c
                for c in ["id_aluno", "nome", "cpf", "email", "status", "data_cadastro"]
                if c in exibicao.columns
            ]

            st.dataframe(exibicao[colunas], use_container_width=True)

            st.markdown("### Gerenciar cadastro")

            ids_disponiveis = exibicao["id_aluno"].dropna().astype(int).tolist()

            if ids_disponiveis:
                id_gerenciar = st.selectbox(
                    "Selecione o ID do aluno",
                    ids_disponiveis,
                    key="id_gerenciar_aluno",
                )

                colg1, colg2, colg3 = st.columns(3)

                with colg1:
                    if st.button("Inativar cadastro", use_container_width=True):
                        ok, msg = inativar_aluno(id_gerenciar)
                        st.success(msg) if ok else st.error(msg)
                        st.rerun()

                with colg2:
                    if st.button("Reativar cadastro", use_container_width=True):
                        ok, msg = reativar_aluno(id_gerenciar)
                        st.success(msg) if ok else st.error(msg)
                        st.rerun()

                with colg3:
                    if st.button("Excluir cadastro", use_container_width=True):
                        ok, msg = excluir_aluno(id_gerenciar)
                        st.success(msg) if ok else st.error(msg)
                        st.rerun()

                with st.form("form_atualizar_email"):
                    st.markdown("### Corrigir e-mail de um cadastro")
                    id_email = st.selectbox(
                        "ID do aluno para atualizar e-mail",
                        ids_disponiveis,
                        key="id_email_aluno",
                    )
                    novo_email = st.text_input("Novo e-mail")
                    salvar_email = st.form_submit_button("Salvar e-mail", use_container_width=True)

                if salvar_email:
                    ok, msg = atualizar_email_aluno(id_email, novo_email)
                    st.success(msg) if ok else st.error(msg)
                    if ok:
                        st.rerun()

                st.download_button(
                    "Baixar cadastro de alunos em CSV",
                    data=alunos.to_csv(index=False).encode("utf-8"),
                    file_name="cadastro_alunos.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

    # =====================================================
    # RANKING
    # =====================================================
    with tab_ranking_publico:
        st.subheader("Ranking geral")

        historico_publico = carregar_historico()

        if historico_publico.empty:
            st.info("Ainda não há ranking disponível.")
        else:
            colunas_ordenacao = [
                c for c in ["nota", "percentual", "tempo_segundos"] if c in historico_publico.columns
            ]

            if colunas_ordenacao:
                ranking = historico_publico.sort_values(
                    by=colunas_ordenacao,
                    ascending=[False, False, True][: len(colunas_ordenacao)],
                ).reset_index(drop=True)
            else:
                ranking = historico_publico.reset_index(drop=True)

            ranking.index = ranking.index + 1

            colunas = [
                c
                for c in [
                    "nome",
                    "materia",
                    "data_realizacao",
                    "nota",
                    "percentual",
                    "tempo",
                    "acertos",
                    "total_questoes",
                ]
                if c in ranking.columns
            ]

            ranking_exibicao = ranking[colunas].copy()

            if "data_realizacao" in ranking_exibicao.columns:
                ranking_exibicao["data_realizacao"] = ranking_exibicao["data_realizacao"].dt.strftime(
                    "%d/%m/%Y %H:%M"
                )

            st.dataframe(ranking_exibicao, use_container_width=True)

# =========================================================
# ÁREA PRIVADA
# =========================================================
else:
    aluno = st.session_state.usuario_logado

    st.markdown("---")
    st.subheader("Painel do aluno")

    col_a, col_b, col_c = st.columns([3, 2, 1])

    with col_a:
        st.success(f"Olá, {aluno['nome']} 👋")
        st.caption(f"ID do aluno: {int(aluno['id_aluno'])}")

    with col_b:
        if bool(aluno.get("troca_senha_pendente")):
            st.warning("Você está usando uma senha temporária. Altere sua senha antes de continuar.")

    with col_c:
        if st.button("Sair", use_container_width=True):
            st.session_state.usuario_logado = None
            st.session_state.prova_iniciada = False
            st.session_state.prova_finalizada = False
            st.session_state.tempo_esgotado = False
            st.session_state.questoes_prova = []
            st.rerun()

    with st.expander("Alterar minha senha"):
        with st.form("form_alterar_senha"):
            senha_atual = st.text_input("Senha atual")
            nova_senha = st.text_input("Nova senha")
            salvar_nova_senha = st.form_submit_button("Salvar nova senha")

        if salvar_nova_senha:
            ok, msg = alterar_senha_usuario(aluno["id_aluno"], senha_atual, nova_senha)
            if ok:
                st.success(msg)
                alunos_atualizados = carregar_alunos()
                atual = alunos_atualizados[
                    pd.to_numeric(alunos_atualizados["id_aluno"], errors="coerce")
                    == int(aluno["id_aluno"])
                ].iloc[0].to_dict()
                st.session_state.usuario_logado = atual
            else:
                st.error(msg)

    questoes = carregar_questoes()

    if not questoes:
        st.warning("Não há questões disponíveis na aba 'questoes'.")
        st.stop()

    materias = sorted(set(q["materia"] for q in questoes))
    tabs_privadas = st.tabs(["Fazer prova", "Meu histórico", "Meu dashboard"])

    # =====================================================
    # FAZER PROVA
    # =====================================================
    with tabs_privadas[0]:
        materia_escolhida = st.selectbox("Filtrar por matéria", ["Todas"] + materias, key="materia_privada")

        if materia_escolhida == "Todas":
            questoes_filtradas = questoes
        else:
            questoes_filtradas = [q for q in questoes if q["materia"] == materia_escolhida]

        col1, col2 = st.columns(2)

        with col1:
            if st.button("Iniciar prova"):
                if not questoes_filtradas:
                    st.warning("Não há questões para a matéria selecionada.")
                else:
                    inicializar_prova(questoes_filtradas)

        with col2:
            if st.button("Reembaralhar"):
                if questoes_filtradas:
                    inicializar_prova(questoes_filtradas)

        if st.session_state.prova_iniciada:
            tempo_passado = int((datetime.now() - st.session_state.inicio_prova).total_seconds())
            tempo_restante = TEMPO_LIMITE - tempo_passado

            if tempo_restante <= 0:
                st.error("⏰ Tempo encerrado! A prova foi finalizada automaticamente.")
                st.session_state.tempo_esgotado = True
                tempo_restante = 0

            st.info(f"⏳ Tempo restante: {formatar_tempo_mmss(tempo_restante)}")

            with st.form("form_prova"):
                respostas = {}

                for i, q in enumerate(st.session_state.questoes_prova, start=1):
                    st.markdown(f"### Questão {i}")
                    st.write(q["pergunta"])

                    opcoes_texto = [o["texto"] for o in q["opcoes_embaralhadas"]]
                    chave_widget = f"q_{st.session_state.tentativa_id}_{q['id']}"

                    if q["tipo"] == "multipla":
                        respostas[str(q["id"])] = st.multiselect(
                            "Selecione uma ou mais alternativas",
                            opcoes_texto,
                            key=chave_widget,
                        )
                    else:
                        respostas[str(q["id"])] = st.radio(
                            "Selecione uma alternativa",
                            opcoes_texto,
                            key=chave_widget,
                            index=None,
                        )

                finalizar = st.form_submit_button("Finalizar prova")

            if finalizar or st.session_state.get("tempo_esgotado", False):
                resumo, detalhes = corrigir_prova(respostas)
                salvar_resultado(aluno, materia_escolhida, resumo)

                st.session_state.prova_finalizada = True
                st.session_state.ultimo_resumo = resumo
                st.session_state.ultimos_detalhes = detalhes
                st.session_state.prova_iniciada = False
                st.session_state.tempo_esgotado = False
                limpar_respostas_da_tentativa()
                st.rerun()

        if st.session_state.prova_finalizada and st.session_state.ultimo_resumo:
            resumo = st.session_state.ultimo_resumo
            detalhes = st.session_state.ultimos_detalhes

            st.success("Prova corrigida com sucesso.")

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Acertos", resumo["acertos"])
            c2.metric("Percentual", f"{resumo['percentual']:.2f}%")
            c3.metric("Nota", resumo["nota"])
            c4.metric("Tempo", resumo["tempo"])

            st.subheader("Detalhamento")
            df_detalhes = pd.DataFrame(detalhes)
            st.dataframe(df_detalhes, use_container_width=True)

            erros = obter_respostas_erradas(detalhes)

            if not erros.empty:
                st.download_button(
                    "Baixar respostas erradas em CSV",
                    data=erros.to_csv(index=False).encode("utf-8"),
                    file_name=f"respostas_erradas_aluno_{int(aluno['id_aluno'])}.csv",
                    mime="text/csv",
                )

    # =====================================================
    # HISTÓRICO
    # =====================================================
    with tabs_privadas[1]:
        historico = carregar_historico()
        meu_historico = preparar_historico_aluno(
            historico,
            aluno["id_aluno"],
            aluno.get("nome"),
            aluno.get("email"),
        )

        st.subheader("Meu histórico")

        if meu_historico.empty:
            st.info("Você ainda não possui resultados salvos.")
        else:
            exibicao = meu_historico.copy().reset_index()

            if "data_realizacao" in exibicao.columns:
                exibicao["data_realizacao"] = exibicao["data_realizacao"].dt.strftime("%d/%m/%Y %H:%M")

            colunas = [
                c
                for c in [
                    "index",
                    "materia",
                    "data_realizacao",
                    "total_questoes",
                    "acertos",
                    "percentual",
                    "nota",
                    "tempo",
                ]
                if c in exibicao.columns
            ]

            tabela = exibicao[colunas].rename(columns={"index": "linha"})
            st.dataframe(tabela, use_container_width=True)
            st.metric("Média das notas", round(pd.to_numeric(meu_historico["nota"], errors="coerce").mean(), 2))

            indice_excluir_visivel = st.number_input(
                "Digite o número da linha que deseja excluir",
                min_value=0,
                max_value=len(tabela) - 1,
                step=1,
                key="excluir_privado",
            )

            if st.button("Excluir tentativa selecionada", key="btn_excluir_privado"):
                indice_real = int(tabela.iloc[int(indice_excluir_visivel)]["linha"])
                excluir_tentativa(indice_real)
                st.success("Tentativa excluída com sucesso.")
                st.rerun()

            st.download_button(
                "Baixar meus resultados em CSV",
                data=meu_historico.to_csv(index=False).encode("utf-8"),
                file_name="meus_resultados.csv",
                mime="text/csv",
                key="download_resultados_privado",
            )

    # =====================================================
    # DASHBOARD
    # =====================================================
    with tabs_privadas[2]:
        historico = carregar_historico()
        meu_historico = preparar_historico_aluno(
            historico,
            aluno["id_aluno"],
            aluno.get("nome"),
            aluno.get("email"),
        )
        exibir_dashboard_evolucao(meu_historico)

st.caption("Sistema com Google Sheets para questões, alunos e resultados")
