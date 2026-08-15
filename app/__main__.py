import os
from .web import run
run(int(os.environ.get("PORT","8798")))
