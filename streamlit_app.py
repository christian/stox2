from __future__ import annotations

from pathlib import Path
import sys

import streamlit as st

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stox.frontend import render_explorer_page, render_settings_page


if __name__ == "__main__":
    st.set_page_config(page_title="stox2", layout="wide")
    navigation = st.navigation(
        [
            st.Page(render_explorer_page, title="Explorer", default=True),
            st.Page(render_settings_page, title="Settings"),
        ],
        position="sidebar",
    )
    navigation.run()
