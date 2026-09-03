import logging

from dotenv import load_dotenv

# Load .env before any module-level os.getenv() captures happen downstream.
load_dotenv()

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from config import STATIC_DIR, ensure_runtime_dirs
from routes import register_routes
from runtime_agents import get_runtime_agents

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

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
