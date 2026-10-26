"""Ponto de entrada do AgroHorti.

Desenvolvimento local:  python app.py
Servidor WSGI (ex.: PythonAnywhere):  from app import app as application
"""
import os

from agrohorti import create_app

app = create_app()

if __name__ == "__main__":
    app.run(
        host=os.environ.get("AGROHORTI_HOST", "127.0.0.1"),
        port=int(os.environ.get("AGROHORTI_PORT", "5000")),
        debug=os.environ.get("FLASK_DEBUG") == "1",
    )
