import unittest

from backend.app.models.customer import Customer
from backend.app.services.template_renderer import render_template


class TemplateRendererTestCase(unittest.TestCase):
    def test_render_customer_variables(self) -> None:
        customer = Customer(phone="+8613800000000", name="张三", source="manual", consent=True)

        result = render_template("你好 {name}，手机号 {phone}，来源 {source}", customer)

        self.assertEqual(result, "你好 张三，手机号 +8613800000000，来源 manual")

    def test_render_name_fallback(self) -> None:
        customer = Customer(phone="+8613800000000", name=None, source=None, consent=True)

        result = render_template("你好 {name}", customer)

        self.assertEqual(result, "你好 客户")


if __name__ == "__main__":
    unittest.main()
