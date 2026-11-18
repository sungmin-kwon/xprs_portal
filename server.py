import logging

from dotenv import load_dotenv

# Load .env before any module-level os.getenv() captures happen downstream.
load_dotenv()

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from config import SERVER_LOG_DIR, SERVER_LOG_FILE_LEVEL, STATIC_DIR, ensure_runtime_dirs
from routes import register_routes
from runtime_agents import get_runtime_agents
from server_logging import configure_file_logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
# Failures used to exist only in the tmux pane; keep them on disk (redacted).
# Must run after basicConfig, which adds the console handler only while the
# root logger has no handlers.
configure_file_logging(SERVER_LOG_DIR, SERVER_LOG_FILE_LEVEL)

ensure_runtime_dirs()

app = FastAPI()
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
register_routes(app)


@app.on_event("startup")
def warm_runtime() -> None:
    logging.info("Preloading XPRS runtime agents at startup...")
    agents = get_runtime_agents()
    gene_df = agents["expl_agent"].gene_agent.data
    app.state.individual_ids = [c for c in gene_df.columns if c != "Gene"]
    logging.info("Runtime warmup complete. Loaded %d individual IDs.", len(app.state.individual_ids))
