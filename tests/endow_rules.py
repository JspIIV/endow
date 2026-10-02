"""The grant rules, with a real escrow, exercised through the real contract methods.

endow.py is loaded against a stub of the runtime, a real Endow is built, and the
assertions go through open_grant() (payable), apply(), review() and cancel(). The stub
controls the page the round fetches, the verdict it returns, and the native value sent,
and it records every emit_transfer. It proves opening a grant escrows the value sent, a
MET verdict pays that escrow to the winning applicant exactly once, an invalid open and a
cancel return the value, and an unreadable delivery pays nothing.

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
    def __init__(self, hex_value): self.as_hex = str(hex_value)
    def __str__(self): return str(self.as_hex)


class _Message:
    def __init__(self):
        self.sender_address = _Address("0x" + "0" * 40)
        self.value = 0


class _Evm:
    """`contract_interface` is a decorator; paying goes through the class it returns,
    whose emit_transfer records (address, value) so a test can assert on real payouts."""
    def __init__(self):
        self.transfers = []
        outer = self

        def contract_interface(cls):
            class Bound:
                def __init__(self, address): self.address = str(address).lower()
                def emit_transfer(self, value): outer.transfers.append((self.address, int(value)))
            return Bound
        self.contract_interface = contract_interface


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
        self.evm = _Evm()
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
REWARD = 500


def answer(verdict, reason="r", quote="q"):
    return json.dumps({"verdict": verdict, "reason": reason, "quote": quote})


def main():
    module, gl = load()

    def as_(address): gl.message.sender_address = _Address(address)
    def value(v): gl.message.value = int(v)

    print("the pure outcome rule")
    check_("MET wins", module._status_for("MET") == "WON")
    check_("UNMET rejects", module._status_for("UNMET") == "REJECTED")
    check_("UNCLEAR stays pending", module._status_for("UNCLEAR") == "PENDING")

    print("\na grant must be funded, and an invalid open returns the value")
    c = fresh(module)
    as_(FUNDER); value(0)
    nofund = json.loads(c.open_grant(TITLE, CRIT))
    check_("an unfunded grant is refused", not nofund["ok"])
    gl.evm.transfers.clear()
    as_(FUNDER); value(REWARD)
    badtitle = json.loads(c.open_grant("", CRIT))
    check_("an invalid open with value is refused", not badtitle["ok"])
    check_("and the value is paid straight back to the funder", gl.evm.transfers == [(FUNDER, REWARD)])

    print("\nopening a grant escrows exactly the value sent")
    gl.evm.transfers.clear()
    as_(FUNDER); value(REWARD)
    g = json.loads(c.open_grant(TITLE, CRIT))
    gid = g["id"]
    check_("a funded grant opens OPEN with reward equal to the value", g["ok"] and g["reward"] == str(REWARD))
    check_("nothing is paid out on open; the escrow is held", gl.evm.transfers == [])
    check_("the open escrow is tracked", json.loads(c.size())["escrow_open"] == str(REWARD))
    value(0)
    check_("the funder cannot apply to their own grant", not json.loads(c.apply(gid, U_GOOD))["ok"])

    print("\napplications are recorded and judged against the funder's criteria")
    as_(ALICE)
    a_bad = json.loads(c.apply(gid, U_BAD))["application"]
    a_unread = json.loads(c.apply(gid, U_UNREAD))["application"]
    as_(BOB)
    a_good = json.loads(c.apply(gid, U_GOOD))["application"]
    check_("three applications are recorded", json.loads(c.status(gid))["applications"] == 3)

    gl.nondet.answer = answer("UNMET", reason="no licence")
    r0 = json.loads(c.review(gid, str(a_bad)))
    check_("an unmet delivery is rejected and the grant stays open", r0["verdict"] == "UNMET" and json.loads(c.status(gid))["status"] == "OPEN")
    check_("the criteria were put in front of the round", CRIT in gl.nondet.last_prompt)
    check_("no escrow moved on an unmet review", gl.evm.transfers == [])

    gl.nondet.web.page = None
    ru = json.loads(c.review(gid, str(a_unread)))
    check_("an unreadable delivery is UNCLEAR and pays nothing", ru["verdict"] == "UNCLEAR" and gl.evm.transfers == [])
    gl.nondet.web.page = "404: Not Found"
    rn = json.loads(c.review(gid, str(a_unread)))
    check_("a not-found delivery is UNCLEAR and pays nothing", rn["verdict"] == "UNCLEAR" and gl.evm.transfers == [])

    print("\nthe first delivery that meets the criteria is PAID the escrow, once")
    gl.nondet.web.page = "a delivery that meets the criteria"
    gl.nondet.answer = answer("MET", reason="CLI, README and MIT licence present")
    rg = json.loads(c.review(gid, str(a_good)))
    check_("a met delivery is AWARDED", rg["awarded"] and rg["status"] == "AWARDED")
    check_("the escrow is transferred to the winning applicant", gl.evm.transfers == [(BOB, REWARD)])
    check_("the award names the winner and the delivery",
           json.loads(c.award(gid))["winner"] == BOB and json.loads(c.award(gid))["delivery_url"] == U_GOOD)

    print("\nan awarded grant is closed and pays no second time")
    gl.evm.transfers.clear()
    check_("no further application can be made", not json.loads(c.apply(gid, "https://example.org/late"))["ok"])
    as_(ALICE); gl.nondet.answer = answer("MET")
    check_("no further review can award it again", not json.loads(c.review(gid, str(a_bad)))["ok"])
    check_("and nothing else is paid out", gl.evm.transfers == [])

    print("\nthe funder can cancel an open grant with no applications and reclaim the escrow")
    gl.evm.transfers.clear()
    as_(FUNDER); value(777)
    g2 = json.loads(c.open_grant("Second grant", CRIT))["id"]
    as_(ALICE)
    check_("a non-funder cannot cancel", not json.loads(c.cancel(g2))["ok"])
    as_(FUNDER)
    canc = json.loads(c.cancel(g2))
    check_("the funder cancels and the escrow is returned", canc["ok"] and gl.evm.transfers == [(FUNDER, 777)])
    check_("a cancelled grant is closed", json.loads(c.status(g2))["status"] == "CANCELLED")
    as_(FUNDER); value(50)
    g3 = json.loads(c.open_grant("Third grant", CRIT))["id"]
    as_(BOB); value(0); c.apply(g3, U_GOOD)
    as_(FUNDER)
    check_("a grant with applications cannot be cancelled", not json.loads(c.cancel(g3))["ok"])

    print("\nthe book counts what it escrowed and awarded")
    size = json.loads(c.size())
    check_("one grant awarded for its reward", size["awarded"] == 1 and size["awarded_units"] == str(REWARD))
    check_("one cancelled, and the open escrow is only the live grant", size["cancelled"] == 1 and size["escrow_open"] == "50")

    failed = [label for label, ok in RESULTS if not ok]
    print()
    if failed:
        print("%d of %d checks failed" % (len(failed), len(RESULTS)))
        return 1
    print("%d checks, all through open_grant(), apply(), review() and cancel() on a real Endow, with a real escrow"
          % len(RESULTS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
