import streamlit.web.cli as stcli
import sys
import os

if __name__ == "__main__":
    sys.argv = ["streamlit", "run", "src/finance_categorizer/main.py"]
    sys.exit(stcli.main())
