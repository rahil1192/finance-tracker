from setuptools import setup, find_packages

setup(
    name="finance_categorizer",
    version="1.0.0",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[
        "streamlit>=1.32.0",
        "pandas>=2.2.0",
        "pdfplumber>=0.10.3",
        "plotly>=5.18.0",
        "fastapi>=0.110.0",
        "uvicorn>=0.27.1",
        "python-multipart>=0.0.9"
    ],
    python_requires=">=3.8",
    include_package_data=True,
    package_data={
        "finance_categorizer": ["*.json"],
    },
)
