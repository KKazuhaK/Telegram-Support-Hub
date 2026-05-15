"""Legacy template renderer entry-point.

Forwards to the new template_engine so existing callers (campaign
builder, imported-target builder) keep working as drop-in replacements
while gaining all the [Random*]/formatting tags.
"""
from backend.app.models.customer import Customer
from backend.app.services.template_engine import render_template_compat


def render_template(body: str, customer: Customer) -> str:
    return render_template_compat(body, customer)
