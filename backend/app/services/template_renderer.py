from backend.app.models.customer import Customer


def render_template(body: str, customer: Customer) -> str:
    return (
        body.replace("{name}", customer.name or "客户")
        .replace("{phone}", customer.phone or "")
        .replace("{source}", customer.source or "")
    )
