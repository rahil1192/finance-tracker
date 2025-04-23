import streamlit.web.cli as stcli
import sys
import os

if __name__ == "__main__":
    sys.argv = ["streamlit", "run", __file__]
    sys.exit(stcli.main())
