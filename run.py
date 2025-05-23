import subprocess
import sys
import os
import uvicorn
from threading import Thread
import logging
import time
import traceback

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def run_streamlit():
    try:
        # Use the main.py from the root backend directory
        main_py = os.path.join(os.path.dirname(__file__), "main.py")
        logger.info(f"Starting Streamlit with {main_py}")
        
        # Check if file exists
        if not os.path.exists(main_py):
            raise FileNotFoundError(f"Streamlit file not found: {main_py}")
            
        process = subprocess.Popen(
            [sys.executable, "-m", "streamlit", "run", main_py],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        
        # Print output in real-time
        while True:
            output = process.stdout.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                print(output.strip())
                
        # Check for errors
        if process.returncode != 0:
            error = process.stderr.read()
            logger.error(f"Streamlit error: {error}")
            raise Exception(f"Streamlit failed with return code {process.returncode}")
            
    except Exception as e:
        logger.error(f"Error running Streamlit: {str(e)}")
        logger.error(traceback.format_exc())
        raise

def run_fastapi():
    try:
        # Add the current directory to Python path
        sys.path.append(os.path.dirname(__file__))
        
        # Use the correct module path
        api_path = "src.finance_categorizer.api"
        logger.info(f"Starting FastAPI server with {api_path}")
        
        uvicorn.run(
            f"{api_path}:app",
            host="0.0.0.0",
            port=8000,
            reload=True,
            log_level="debug"
        )
    except Exception as e:
        logger.error(f"Error running FastAPI: {str(e)}")
        logger.error(traceback.format_exc())
        raise

if __name__ == "__main__":
    try:
        # Start Streamlit in a separate thread
        logger.info("Starting Streamlit thread")
        streamlit_thread = Thread(target=run_streamlit)
        streamlit_thread.daemon = True  # Thread will exit when main program exits
        streamlit_thread.start()
        
        # Give Streamlit time to start
        time.sleep(2)
        
        # Run FastAPI in the main thread
        logger.info("Starting FastAPI server")
        run_fastapi()
    except Exception as e:
        logger.error(f"Error in main: {str(e)}")
        logger.error(traceback.format_exc())
        sys.exit(1)
