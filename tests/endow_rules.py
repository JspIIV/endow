"""The grant rules, exercised through the real contract methods.

endow.py is loaded against a stub of the runtime, a real Endow is built, and the
assertions go through open_grant(), apply() and review(). The stub controls the page the
round fetches and the verdict it returns. It proves the delivery is judged against the
funder's fixed criteria, that only a MET awards the reward, that only the first one does,
that an unreadable delivery awards nothing, that a funder cannot apply to their own grant,
and that an awarded grant is closed.

    python tests/endow_rules.py
"""

import io
import json
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
CONTRACT = os.path.join(HERE, "..", "contracts", "endow.py")


class _Store:
    def __init__(self, kind): self.kind = kind
    def __class_getitem__(cls, item): return cls("map" if isinstance(item, tuple) else "list")
    def make(self): return {} if self.kind == "map" else []


class _Address:
    def __init__(self, hex_value): self.as_hex = hex_value
    def __str__(self): return str(self.as_hex)


class _Message:
    def __init__(self):
        self.sender_address = _Address("0x" + "0" * 40)
        self.value = 0


class _Web:
    def __init__(self):
        self.page = "a delivery"

    def render(self, url):
        if self.page is None:
            raise RuntimeError("could not fetch")
        return self.page


class _Nondet:
    def __init__(self, web):
        self.web = web
        self.last_prompt = None
        self.answer = "{}"

    def exec_prompt(self, task):
        self.last_prompt = task
        return self.answer


class _Write:
    def __call__(self, fn): return fn
    def payable(self, fn): return fn


class _PublicNS:
    def __init__(self):
        self.write = _Write()
        self.view = lambda fn: fn


class _EqPrinciple:
    def prompt_comparative(self, run, principle=None): return run()


class _GL:
    def __init__(self):
        self.Contract = object
        self.public = _PublicNS()
        self.message = _Message()
        self.nondet = _Nondet(_Web())
        self.eq_principle = _EqPrinciple()


def load():
    gl = _GL()
    fake = types.ModuleType("genlayer")
    fake.gl = gl
    fake.DynArray = _Store
    fake.TreeMap = _Store
    fake.u32 = int
    fake.u256 = int
    fake.Address = _Address
    sys.modules["genlayer"] = fake
    module = types.ModuleType("endow_under_test")
    exec(compile(io.open(CONTRACT, encoding="utf-8").read(), CONTRACT, "exec"), module.__dict__)
    return module, gl


def fresh(module):
    contract = module.Endow.__new__(module.Endow)
    for field, declared in module.Endow.__annotations__.items():
        setattr(contract, field, declared.make())
    contract.__init__()
    return contract


RESULTS = []


def check_(label, condition):
    RESULTS.append((label, bool(condition)))
    print(("  ok  " if condition else " FAIL "), label)


FUNDER = "0x1111111111111111111111111111111111111111"
ALICE = "0x2222222222222222222222222222222222222222"
BOB = "0x3333333333333333333333333333333333333333"

CRIT = "An open-source CLI that converts CSV to JSON, with a README and an OSI-approved licence."
TITLE = "csv2json grant"
U_BAD = "https://example.org/bad"
U_GOOD = "https://example.org/good"
U_UNREAD = "https://example.org/gone"


def answer(verdict, reason="r", quote="q"):
    return json.dumps({"verdict": verdict, "reason": reason, "quote": quote})


def bal(c, who):
    return json.loads(c.balance(who))["balance"]


def main():
    module, gl = load()

    def as_(address): gl.message.sender_address = _Address(address)

    print("the pure outcome rule")
    check_("MET wins", module._status_for("MET") == "WON")
    check_("UNMET rejects", module._status_for("UNMET") == "REJECTED")
    check_("UNCLEAR stays pending", module._status_for("UNCLEAR") == "PENDING")

    print("\nopening a grant and applying")
    c = fresh(module)
    as_(FUNDER)
    check_("a zero reward is refused", not json.loads(c.open_grant(TITLE, CRIT, "0"))["ok"])
    g = json.loads(c.open_grant(TITLE, CRIT, "500"))
    gid = g["id"]
    check_("a good grant opens OPEN", g["ok"] and g["status"] == "OPEN")
    check_("the funder cannot apply to their own grant", not json.loads(c.apply(gid, U_GOOD))["ok"])
    as_(ALICE)
    a_bad = json.loads(c.apply(gid, U_BAD))["application"]
    a_unread = json.loads(c.apply(gid, U_UNREAD))["application"]
    as_(BOB)
    a_good = json.loads(c.apply(gid, U_GOOD))["application"]
    check_("three applications are recorded", json.loads(c.status(gid))["applications"] == 3)

    print("\na delivery that misses the criteria is UNMET and the grant stays open")
    gl.nondet.answer = answer("UNMET", reason="no licence stated")
    r0 = json.loads(c.review(gid, str(a_bad)))
    check_("an unmet delivery is rejected", r0["verdict"] == "UNMET" and json.loads(c.status(gid))["status"] == "OPEN")
    check_("the criteria were put in front of the round", CRIT in gl.nondet.last_prompt)
    check_("no reward moved", bal(c, ALICE) == 0)

    print("\nan unreadable delivery is UNCLEAR and awards nothing")
    gl.nondet.web.page = None
    ru = json.loads(c.review(gid, str(a_unread)))
    check_("an unreadable delivery is UNCLEAR and the grant stays open", ru["verdict"] == "UNCLEAR" and json.loads(c.status(gid))["status"] == "OPEN")
    gl.nondet.web.page = "404: Not Found"
    rn = json.loads(c.review(gid, str(a_unread)))
    check_("a not-found delivery is UNCLEAR and awards nothing", rn["verdict"] == "UNCLEAR" and bal(c, ALICE) == 0)

    print("\nthe first delivery that meets the criteria is awarded the reward")
    gl.nondet.web.page = "a delivery meeting the criteria"
    gl.nondet.answer = answer("MET", reason="CLI, README and MIT licence all present")
    rg = json.loads(c.review(gid, str(a_good)))
    check_("a met delivery is AWARDED", rg["awarded"] and rg["status"] == "AWARDED")
    check_("the reward is credited to the applicant", bal(c, BOB) == 500)
    check_("the award names the winner and the delivery",
           json.loads(c.award(gid))["winner"] == BOB and json.loads(c.award(gid))["delivery_url"] == U_GOOD)

    print("\nan awarded grant is closed")
    check_("no further application can be made", not json.loads(c.apply(gid, "https://example.org/late"))["ok"])
    as_(ALICE)
    gl.nondet.answer = answer("MET")
    check_("no further review can award it again", not json.loads(c.review(gid, str(a_bad)))["ok"])
    check_("the winner keeps exactly the one reward", bal(c, BOB) == 500)

    print("\nthe book counts what it awarded")
    size = json.loads(c.size())
    check_("one grant, awarded, for its reward", size["awarded"] == 1 and size["awarded_units"] == 500 and size["open"] == 0)

    failed = [label for label, ok in RESULTS if not ok]
    print()
    if failed:
        print("%d of %d checks failed" % (len(failed), len(RESULTS)))
        return 1
    print("%d checks, all through open_grant(), apply() and review() on a real Endow"
          % len(RESULTS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
