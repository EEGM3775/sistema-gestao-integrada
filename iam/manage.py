#!/usr/bin/env python
"""Utilitário de linha de comando do serviço IAM."""
import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "iam_project.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Não foi possível importar o Django. Ative o ambiente virtual e "
            "instale as dependências (requirements.txt)."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
