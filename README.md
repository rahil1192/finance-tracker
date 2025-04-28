# Finance Categorizer

A production-ready application for categorizing and analyzing financial transactions from PDF statements.

## Features

- Upload and process PDF bank statements
- Automatic vendor categorization
- Transaction analysis and visualization
- Persistent storage of transaction history
- Customizable vendor mapping
- User-friendly interface

## Installation

1. Clone the repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Configuration

The application can be configured through `config.yaml`:

- `data`: File paths and storage settings
- `ui`: Interface customization
- `processing`: Data processing limits and formats

## Usage

1. Start the application:

   ```bash
   streamlit run main.py
   ```

2. Upload PDF bank statements
3. View and categorize transactions
4. Analyze spending patterns
5. Export categorized data

## Error Handling

The application includes comprehensive error handling:

- File validation
- Data processing errors
- User input validation
- Logging to file and console

## Performance

- Caching for frequently accessed data
- Optimized data processing
- Efficient file handling

## Contributing

1. Fork the repository
2. Create a feature branch
3. Submit a pull request

## License

MIT License

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
