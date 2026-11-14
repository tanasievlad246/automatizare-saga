"""Build the demo data to try the program against, without ANAF, OpenRouter or SAGA.

    uv run python scripts/seed_demo.py

Everything goes into demo/ (ignored by git); the building itself is in efactura.demo.
"""

from efactura import demo

if __name__ == "__main__":
    demo.build(demo.FOLDER)
    print("Ready. Start it with: uv run efactura demo")
