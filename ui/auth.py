"""Barreira de autenticação antes da navegação ou consulta aos dados."""
import streamlit as st

from services.auth import (LOGIN_LIMITER, authenticated, load_password_hash,
                           sign_in, verify_password)


def clear_session():
    st.session_state.clear()
    # Download do Streamlit usa referências de mídia da sessão. Revoga os
    # arquivos que não estejam sendo usados por outra sessão autenticada.
    from streamlit import runtime
    if runtime.exists():
        manager = runtime.get_instance().media_file_mgr
        manager.clear_session_refs()
        manager.remove_orphaned_files()
        manager.remove_orphaned_files()


def require_login():
    try:
        password_hash = load_password_hash()
    except ValueError as exc:
        clear_session()
        st.title("Minhas finanças")
        st.error(str(exc))
        st.info("Defina a senha no terminal do PC. Não informe sua senha no GitHub ou em conversas.")
        st.stop()
    if authenticated(st.session_state, password_hash):
        return
    # Remove também exportações, arquivos importados e seleções da sessão antiga.
    if "_auth_token" in st.session_state or "_exports" in st.session_state:
        clear_session()
    st.title("Minhas finanças")
    st.caption("Acesso privado · Entre com sua senha para continuar.")
    with st.form("login", clear_on_submit=True):
        password = st.text_input("Senha", type="password", key="login_password", max_chars=72)
        submitted = st.form_submit_button("Entrar", type="primary")
    if submitted:
        remaining = LOGIN_LIMITER.remaining()
        if remaining:
            st.error(f"Muitas tentativas. Aguarde {remaining} segundos e tente novamente.")
        elif verify_password(password, password_hash):
            sign_in(st.session_state, password_hash)
            st.rerun()
        else:
            LOGIN_LIMITER.failure()
            st.error("Senha incorreta.")
    st.stop()


def logout_button():
    if st.button("Sair", key="logout"):
        clear_session()
        st.rerun()
