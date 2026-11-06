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


def _attempt_login():
    """Callback: valida antes de renderizar a próxima página, sem tela obsoleta."""
    try:
        password_hash = load_password_hash()
    except ValueError:
        clear_session()
        return
    remaining = LOGIN_LIMITER.remaining()
    if remaining:
        st.session_state['_login_error'] = f'Muitas tentativas. Aguarde {remaining} segundos e tente novamente.'
    elif verify_password(st.session_state.get('login_password', ''), password_hash):
        sign_in(st.session_state, password_hash)
    else:
        LOGIN_LIMITER.failure()
        st.session_state['_login_error'] = 'Senha incorreta.'


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
    if "_auth_token" in st.session_state or "_exports" in st.session_state:
        clear_session()
    with st.container(key='glass_login'):
        st.html('<p class="eyebrow">Seu espaço, só seu</p>')
        st.title("Minhas finanças")
        st.caption("Mais clareza para cuidar do que importa. Entre com sua senha para continuar.")
        with st.form("login", clear_on_submit=True):
            st.text_input("Senha", type="password", key="login_password", max_chars=72)
            st.form_submit_button("Entrar", type="primary", width='stretch', on_click=_attempt_login)
        message = st.session_state.pop('_login_error', None)
        if message:
            st.error(message)
        st.caption('Acesso privado · Dados no seu PC')
    st.stop()


def logout_button():
    if st.button("Sair", key="logout"):
        clear_session()
        st.rerun()
