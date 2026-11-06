"""Entry gate for isolated public demo workspaces."""
import streamlit as st

from treasurer import session_store
from treasurer.demo_workspace import create_workspace, public_demo, workspace_path
from ui.common import OUT, STEPS, ss


def enter() -> None:
    if not public_demo() or ss.get("_demo_code"):
        return
    st.header("Try Tallyable")
    st.write("Use the sample receipts to try closing out an event. Your demo workspace is separate from other testers.")
    st.caption("Save your private return code to reopen your work. Anyone with that code can access this workspace.")
    if st.button("Start my demo", type="primary"):
        ss._demo_code = create_workspace(OUT)
        st.rerun()
    with st.form("resume-demo"):
        code = st.text_input("Return code", type="password").strip()
        resume = st.form_submit_button("Resume my demo")
    if resume:
        try:
            folder = workspace_path(OUT, code)
        except ValueError:
            folder = None
        if folder is None or not folder.is_dir():
            st.error("That workspace wasn't found. Check the code, or start a new demo.")
        else:
            ss._demo_code = code
            saved = session_store.load(folder / "session.json")
            if saved:
                ss.update(saved)
                ss.step = saved.get("step") if saved.get("step") in STEPS else STEPS[0]
            st.rerun()
    st.stop()


def return_code() -> None:
    if not public_demo():
        return
    with st.sidebar.expander("Save your return code"):
        st.code(ss._demo_code, language=None)
        st.caption("Keep this private. Use it to resume after visiting the home page. "
                   "Demo storage may be cleared; download your results.")
