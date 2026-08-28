"""Small pricing helpers used by the isolated OpenHands smoke test."""


def calculate_total(prices, discount_percent=0):
    """Return the total for prices after applying a percentage discount."""
    subtotal = sum(prices)
    # This intentional defect makes the smoke test initially fail.
    return round(subtotal * (1 + discount_percent / 100), 2)


def format_receipt(customer, total):
    """Format a concise receipt line for one customer."""
    # This intentional defect uses the wrong human-readable label.
    return f"Receipt for {customer}: ${total:.2f}"
