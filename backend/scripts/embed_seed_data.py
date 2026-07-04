"""
embed_seed_data.py — Utility script to generate embeddings for seed KB articles.

This script fetches any knowledge_base rows where embedding IS NULL,
generates a 768-dim vector using Gemini, and updates the row.

Run this script once after executing sql/002_seed_knowledge_base.sql:
    python -m scripts.embed_seed_data
"""

import sys
import os

# Add backend directory to sys.path so we can import app modules
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

import structlog
from app.database import get_supabase_client
from app.services.gemini_service import get_gemini_service

log = structlog.get_logger(__name__)

def run() -> None:
    client = get_supabase_client()
    gemini = get_gemini_service()

    log.info("Fetching KB articles with NULL embeddings...")
    response = client.table("knowledge_base").select("id, title, content").is_("embedding", "null").execute()
    
    articles = response.data
    if not articles:
        log.info("No articles found needing embeddings. You are all set!")
        return

    log.info(f"Found {len(articles)} articles. Generating embeddings...")

    for article in articles:
        text_to_embed = f"Title: {article['title']}\n\n{article['content']}"
        log.info("Embedding article", id=article["id"], title=article["title"])
        
        try:
            embedding = gemini.generate_embedding(text_to_embed)
            
            # Update row in supabase
            client.table("knowledge_base").update({"embedding": embedding}).eq("id", article["id"]).execute()
            log.info("Successfully updated article", id=article["id"])
        except Exception as e:
            log.error("Failed to embed article", id=article["id"], error=str(e))
            
    log.info("Finished embedding seed data.")

if __name__ == "__main__":
    run()
