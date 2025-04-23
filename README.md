# Finance Statement Categorizer

A Streamlit application for categorizing and analyzing financial statements from PDF files.

## Features

- Upload and parse PDF bank statements
- Automatic transaction categorization
- Interactive data editing and visualization
- Monthly expense reports
- Custom category management
- Vendor mapping for automatic categorization

## Installation

1. Clone the repository
2. Install dependencies:

```bash
pip install -r requirements.txt
```

## Usage

Run the application:

```bash
streamlit run src/finance_categorizer/main.py
```

## Project Structure

```
finance_categorizer/
├── src/
│   └── finance_categorizer/
│       ├── models/         # Data models and processing
│       ├── utils/          # Utility functions
│       ├── ui/             # UI components
│       └── main.py         # Main application entry point
├── saved_statements/       # Directory for saved PDF statements
├── requirements.txt        # Project dependencies
└── README.md              # Project documentation
```

## Configuration

- Vendor mappings are stored in `vendor_map.json`
- Custom categories are saved in the application state
- PDF statements are saved in the `saved_statements` directory
