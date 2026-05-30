"""Enable ``python -m sifty`` as an alternative to the ``sifty`` console script."""

from .cli import entrypoint

if __name__ == "__main__":
    entrypoint()
