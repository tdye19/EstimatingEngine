"""APEX Spec Retrieval Module — semantic search over project specifications.

Critical path for demo:
  1. index_project_specs(db, project_id) — after Agent 2 parses specs
  2. search(project_id, query, top_k=5) — called by Agent 3 + Agent 6
"""
