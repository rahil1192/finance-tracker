import streamlit.web.cli as stcli
import sys
import os

if __name__ == "__main__":
    # Add the src directory to Python path
    src_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "src"))
    sys.path.insert(0, src_path)

    # Run the application
    sys.argv = ["streamlit", "run", os.path.join(
        src_path, "finance_categorizer", "main.py")]
    sys.exit(stcli.main())
