"""Tema local: sem fontes, imagens ou scripts externos."""
from pathlib import Path
import streamlit as st


def apply_styles():
    st.html('<style>' + Path(__file__).with_name('styles.css').read_text(encoding='utf-8') + '</style>')
