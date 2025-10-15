def test_packages_importable():
    __import__("backend")
    __import__("backend.products")
    __import__("backend.products.mahnwesen")
    __import__("backend.products.erechnung")
    __import__("agents")
    __import__("agents.mahnwesen")
    __import__("agents.erechnung")
