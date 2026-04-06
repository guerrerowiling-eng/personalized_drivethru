"""Menú Café Barista (Guatemala) — categorías e ítems seleccionables."""

MENU_CATEGORIES: list[dict[str, list[str]]] = [
    {
        "titulo": "Bebidas calientes",
        "items": [
            "Café Guatemalteco / Café de la Casa (12oz)",
            "Café Guatemalteco / Café de la Casa (16oz)",
            "Americano (12oz)",
            "Americano (16oz)",
            "Cappuccino (12oz)",
            "Cappuccino (16oz)",
            "Latte (12oz)",
            "Latte (16oz)",
            "Bianca Mocca (12oz)",
            "Bianca Mocca (16oz)",
            "Mocca (12oz)",
            "Mocca (16oz)",
            "Caramel Macchiato (12oz)",
            "Caramel Macchiato (16oz)",
            "Matcha Latte caliente (12oz)",
            "Matcha Latte caliente (16oz)",
            "Chocolate Caliente (12oz)",
            "Chocolate Caliente (16oz)",
            "Infusión / Té — Manzanilla",
            "Infusión / Té — Té negro",
        ],
    },
    {
        "titulo": "Bebidas frías",
        "items": [
            "Iced Coffee (12oz)",
            "Iced Coffee (16oz)",
            "Iced Latte (12oz)",
            "Iced Latte (16oz)",
            "Iced Americano (12oz)",
            "Iced Americano (16oz)",
            "Frappé Mocca (12oz)",
            "Frappé Mocca (16oz)",
            "Frappé Caramel (12oz)",
            "Frappé Caramel (16oz)",
            "Frappé Bianca Mocca (12oz)",
            "Frappé Bianca Mocca (16oz)",
            "Matcha Frío (12oz)",
            "Matcha Frío (16oz)",
        ],
    },
    {
        "titulo": "Desayunos",
        "items": [
            "Huevos al gusto con frijoles, plátanos y pan artesanal",
            "Bocata de desayuno jamón y queso",
            "Bocata de desayuno atún",
        ],
    },
    {
        "titulo": "Sándwiches y bocatas",
        "items": [
            "Bocata jamón y queso",
            "Bocata atún",
            "Bocata pollo",
            "Croissant jamón y queso",
            "Panini jamón y queso",
            "Panini atún",
            "Panini pollo",
            "Panini vegetariano",
        ],
    },
    {
        "titulo": "Ensaladas y almuerzos",
        "items": [
            "Ensalada César con pollo",
            "Ensalada Primavera",
            "Combo lunch (panini o bocata + bebida)",
        ],
    },
    {
        "titulo": "Postres",
        "items": [
            "Cheesecake",
            "Banana Bread",
            "Bundt Cake",
            "Muffin",
            "Croissant dulce",
            "Galletas",
        ],
    },
]


def all_menu_items() -> list[str]:
    out: list[str] = []
    for cat in MENU_CATEGORIES:
        out.extend(cat["items"])
    return out


def is_valid_order(text: str) -> bool:
    t = (text or "").strip()
    return t in set(all_menu_items())
