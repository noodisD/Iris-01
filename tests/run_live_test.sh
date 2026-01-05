#!/bin/bash
export OPENAI_API_KEY=$(grep OPENAI_API_KEY .env | cut -d '=' -f2)
export PYTHONPATH=$PYTHONPATH:.
pytest tests/test_live_system.py -s
