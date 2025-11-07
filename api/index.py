"""
Vercel Serverless Function Entry Point

Este arquivo é necessário para o Vercel reconhecer a aplicação FastAPI.
Vercel espera encontrar 'app' neste arquivo.
"""

import sys
import os

# Adiciona diretório raiz ao Python path para imports funcionarem
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Importa a aplicação FastAPI
from src.main import app

# Vercel vai usar esta variável 'app'
__all__ = ['app']

