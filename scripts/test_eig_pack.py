"""Run inside Streamlit/runtime environment where EIG_EMAIL/EIG_PASSWORD exist.
Never prints credentials or tokens.
"""
import os
from eig_client import EIGClient

email = os.getenv("EIG_EMAIL")
password = os.getenv("EIG_PASSWORD")
if not email or not password:
    raise SystemExit("EIG_EMAIL/EIG_PASSWORD not present in environment")

client = EIGClient(email, password)
title, docs = client.pack(1433491)
print("PACK", title)
print("DOCUMENTS", len(docs))
for d in docs[:12]:
    print(d.priority, d.name, d.updated or "", d.size or "")
