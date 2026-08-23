from pprint import pprint
from db import init_db
from registry import run_all

if __name__=="__main__":
    init_db()
    pprint(run_all(max_guide=300000))
