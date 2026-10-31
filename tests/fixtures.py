"""Synthetic repo covering the parsing and import cases the index must survive."""
from __future__ import annotations

MODELS = '''"""Shop models."""
from dataclasses import dataclass
MAX_ITEMS = 100
DEFAULT_CURRENCY: str = "USD"
LONG_TABLE = {"alpha": 1, "beta": 2, "gamma": 3, "delta": 4, "epsilon": 5, "zeta": 6, "eta": 7}
lowercase = 1


@dataclass
class Cart:
    """A shopping cart."""
    items: list = None
    owner: str = ""

    class Meta:
        ordering = ["id"]

        class Deep:
            level: int = 3

    def add(self, item, qty: int = 1) -> None:
        for _ in range(qty):
            pass

    @property
    def total(self) -> float:
        def helper(): return 1
        return helper()

    async def sync(self,
                   remote: str,
                   *,
                   force: bool = False) -> bool:
        return True

    def tiny(self): return 1


class Coupon(Cart): pass


def free(x): return x


def documented(a: int) -> int:
    """Doc here."""
    return a
'''

FIXTURE = {
    "app.py": "from srclib.core import run\nimport requests\n\n\ndef main():\n    return run()\n",
    "consumer.py": "from shop import Cart\nfrom shop import billing\nfrom shop.missing import nothing\n",
    "shop/__init__.py": '"""Shop package."""\nfrom .models import Cart\n',
    "shop/models.py": MODELS,
    "shop/billing.py": (
        "from .models import Cart, Coupon\nfrom .utils import CouponValidator\n\n\n"
        "class PriceCalculator:\n    def inject(self, c):\n        return CouponValidator().validate(c)\n"
    ),
    "shop/utils.py": (
        "from .billing import PriceCalculator\nimport decimal\n\n\n"
        "class CouponValidator:\n    def validate(self, code):\n        return PriceCalculator\n"
    ),
    "src/srclib/__init__.py": "",
    "src/srclib/core.py": "import json\n\n\ndef run():\n    return json.dumps({})\n",
    "packages/x/src/xpkg/__init__.py": "",
    "packages/x/src/xpkg/thing.py": "def thing():\n    return 1\n",
    "use_x.py": "import xpkg.thing\nfrom xpkg import thing as t\n",
    "ns/mod.py": "def m():\n    pass\n",
    "ns/other.py": "from . import mod\nimport ns.mod\nfrom .. import toohigh\n",
    "broken.py": "def oops(:\n    pass\n\nclass Fine:\n    pass\n",
    "latin.py": b"# caf\xe9\ndef f(): return 1\n",
    "uni.py": "def größe(): pass\n\n\nclass Ünï:\n    def méthode(self): pass\n",
    "newer.py": "type Alias = int\n\n\nclass Box[T]:\n    pass\n",
    "empty.py": "",
}
