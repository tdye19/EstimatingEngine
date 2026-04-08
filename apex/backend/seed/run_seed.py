import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from apex.backend.seed.load_decision_data import run

run()
