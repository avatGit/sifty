"""Enable ``python -m sifty`` as an alternative to the ``sifty`` console script."""

from .cli import app

if __name__ == "__main__":
    app()
