import sqlite3

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event
from sqlalchemy.engine import Engine

db = SQLAlchemy()


@event.listens_for(Engine, "connect")
def _ativar_chaves_estrangeiras(conexao, _registro):
    # O SQLite só verifica chaves estrangeiras quando isso é ativado em cada conexão.
    if isinstance(conexao, sqlite3.Connection):
        cursor = conexao.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
