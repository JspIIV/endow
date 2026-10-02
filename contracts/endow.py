# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
"""Endow: an open-criteria grant that escrows a real reward and pays the first delivery a round judges to meet the criteria.

A grant is usually decided behind closed doors, and the criteria bend to the choice.
Endow fixes the criteria first, in public, and backs the reward with real value. A funder
opens a grant by sending the reward as native value, which the contract holds in escrow.
Anyone applies by naming one public page as their delivery. Then anyone can ask the contract
to review an application: it fetches that page and a round of GenLayer validators reads it
against the funder's fixed criteria. The first delivery judged to meet them is paid the
escrowed reward, once, and the grant closes.

The money is real. Opening a grant debits the funder, the escrow is held by the contract,
and the winning applicant receives it exactly once through a native transfer. If no one has
applied yet, the funder can cancel and take the escrow back.

## What it settles, per application

    MET      the delivery meets the criteria -> the FIRST such application is PAID the escrow
    UNMET    the delivery was read and does not meet the criteria -> that application is rejected
    UNCLEAR  the delivery could not be read, or does not settle it -> nothing changes

Only MET pays, only the first one, and only while the grant is open.

## What it refuses

The criteria are fixed when the grant is opened and cannot be edited. A grant must be funded:
open_grant is payable and the reward is exactly the value sent. A funder cannot apply to their
own grant. An application is bound to its applicant, and the escrow is paid to that applicant.
An unreadable delivery pays nothing. Once paid or cancelled a grant is closed for good.

## Where it stops, plainly

It judges a delivery against criteria in words, which is a judgement, not a proof: write
criteria a stranger could apply the same way twice, and accept a delivery a third party can
open. It pays the first delivery that meets the bar, not the best one. Native value moves on
Studio; it is held and paid here through the standard payable and emit_transfer path.
"""

from genlayer import *
import json

MET = "MET"
UNMET = "UNMET"
UNCLEAR = "UNCLEAR"
VERDICTS = (MET, UNMET, UNCLEAR)

OPEN = "OPEN"
AWARDED = "AWARDED"
CANCELLED = "CANCELLED"

PENDING = "PENDING"
REJECTED = "REJECTED"
WON = "WON"

MAX_TITLE = 160
MAX_CRITERIA = 500
MAX_URL = 300
MAX_PAGE = 6000
MAX_REASON = 300
MAX_QUOTE = 300
MAX_APPS = 100

FETCH_FAILED = "__FETCH_FAILED__"


@gl.evm.contract_interface
class _Recipient:
    """An externally owned account we pay native value to, in the faucet.py style."""
    class View:
        pass

    class Write:
        pass


def _pay(addr: str, amount: int) -> None:
    _Recipient(Address(addr)).emit_transfer(value=int(amount))


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _clip(text: str, limit: int) -> str:
    text = str(text).strip()
    return text if len(text) <= limit else text[:limit] + " [...]"


def _whole(value) -> int:
    try:
        return int(str(value).strip())
    except Exception:
        return -1


def _addr(value) -> str:
    text = str(value).strip().lower()
    if not text.startswith("0x") or len(text) != 42:
        return ""
    for character in text[2:]:
        if character not in "0123456789abcdef":
            return ""
    return text


def _url_ok(url: str) -> bool:
    text = str(url).strip()
    if len(text) < 8 or len(text) > MAX_URL or " " in text:
        return False
    return text.startswith("https://") or text.startswith("http://")


def _status_for(verdict: str) -> str:
    """Only MET awards; UNMET rejects the application; UNCLEAR leaves it to be reviewed again."""
    if verdict == MET:
        return WON
    if verdict == UNMET:
        return REJECTED
    return PENDING


def _field(raw: str, name: str, allowed, fallback: str) -> str:
    try:
        text = str(raw).strip()
        obj = json.loads(text[text.index("{"):text.rindex("}") + 1])
        if isinstance(obj, dict):
            said = str(obj.get(name, "")).strip().upper()
            return said if said in allowed else fallback
    except Exception:
        pass
    return fallback


def _text_field(raw: str, name: str, limit: int) -> str:
    try:
        text = str(raw).strip()
        obj = json.loads(text[text.index("{"):text.rindex("}") + 1])
        if isinstance(obj, dict):
            return _clip(str(obj.get(name, "")), limit)
    except Exception:
        pass
    return ""


def _task(title: str, criteria: str, delivery: str) -> str:
    return f"""A grant published fixed criteria and escrowed a reward. An applicant has submitted the
page below as their delivery. Read the delivery and decide whether it meets the criteria.

THE GRANT:
{title}

THE CRITERIA (fixed before any application, all must be satisfied):
{criteria}

THE APPLICANT'S DELIVERY:
{delivery}

Decide one of:
  {MET} the delivery satisfies the criteria
  {UNMET} the delivery was read and does not satisfy the criteria (a requirement is missing or unmet)
  {UNCLEAR} the delivery could not be read, or does not give enough to tell whether it meets the criteria

Judge the delivery only against the criteria as written, evenly. Every stated requirement must
be met for {MET}; if any is missing, that is {UNMET}. A page that is an error page, a "404" or
"not found" notice, an empty page, or a page unrelated to the grant is not a delivery you can
judge: that is {UNCLEAR}, never {MET}.

Reply with bare JSON and nothing else:
{{"verdict": "{MET}" or "{UNMET}" or "{UNCLEAR}",
  "quote": "the passage that decided it, or empty",
  "reason": "one sentence naming what decided it against the criteria"}}"""


class Endow(gl.Contract):
    """Open-criteria grants, each escrowing a real reward paid to the first delivery that meets the criteria."""

    # str(id) -> the grant as JSON, including its applications.
    items: TreeMap[str, str]
    ids: DynArray[str]

    def __init__(self) -> None:
        pass

    @gl.public.write.payable
    def open_grant(self, title: str, criteria: str) -> str:
        """Open a grant by sending the reward as native value. Bound to the caller (the funder).

        The reward is exactly the value attached; the contract holds it in escrow. This method
        never raises once value is attached: on any invalid input the value is paid straight
        back to the funder and nothing is created.
        """
        funder = gl.message.sender_address.as_hex.lower()
        value = int(gl.message.value)
        ttl = _clip(title, MAX_TITLE)
        crit = _clip(criteria, MAX_CRITERIA)

        problem = ""
        if value <= 0:
            problem = "a grant must be funded; attach the reward as native value"
        elif not ttl:
            problem = "give the grant a title"
        elif len(crit) < 12:
            problem = "state the criteria in plain words"
        if problem:
            if value > 0:
                _pay(funder, value)  # refund, never keep an unaccepted deposit
            return json.dumps({"ok": False, "error": problem, "refunded": value})

        gid = str(len(self.ids))
        record = {
            "id": gid,
            "funder": funder,
            "opened_at": _now_iso(),
            "title": ttl,
            "criteria": crit,
            "reward": str(value),
            "status": OPEN,
            "reviews": 0,
            "winner": "",
            "winning_app": -1,
            "awarded_at": "",
            "applications": [],
        }
        self.items[gid] = json.dumps(record)
        self.ids.append(gid)
        return json.dumps({"ok": True, "id": gid, "status": OPEN, "reward": str(value)})

    @gl.public.write
    def apply(self, grant_id: str, delivery_url: str) -> str:
        """Apply to a grant by naming one public page as your delivery. Bound to the caller (the applicant)."""
        applicant = gl.message.sender_address.as_hex.lower()
        gid = str(grant_id).strip()
        link = str(delivery_url).strip()
        stored = self.items.get(gid, None)
        if stored is None:
            return json.dumps({"ok": False, "error": "no grant with that id"})
        record = json.loads(stored)
        if record["status"] != OPEN:
            return json.dumps({"ok": False, "error": "this grant is already " + record["status"].lower(),
                               "status": record["status"]})
        if applicant == record["funder"]:
            return json.dumps({"ok": False, "error": "the funder cannot apply to their own grant"})
        if not _url_ok(link):
            return json.dumps({"ok": False, "error": "give an http(s) URL for your delivery"})
        apps = list(record.get("applications", []))
        if len(apps) >= MAX_APPS:
            return json.dumps({"ok": False, "error": "this grant has reached its application limit"})

        idx = len(apps)
        apps.append({"i": idx, "applicant": applicant, "delivery_url": link, "status": PENDING,
                     "verdict": "", "reason": "", "quote": "", "at": _now_iso()})
        record["applications"] = apps
        self.items[gid] = json.dumps(record)
        return json.dumps({"ok": True, "grant_id": gid, "application": idx, "status": PENDING})

    @gl.public.write
    def cancel(self, grant_id: str) -> str:
        """The funder may cancel an open grant that has no applications yet, and reclaim the escrow."""
        who = gl.message.sender_address.as_hex.lower()
        gid = str(grant_id).strip()
        stored = self.items.get(gid, None)
        if stored is None:
            return json.dumps({"ok": False, "error": "no grant with that id"})
        record = json.loads(stored)
        if record["status"] != OPEN:
            return json.dumps({"ok": False, "error": "only an open grant can be cancelled", "status": record["status"]})
        if who != record["funder"]:
            return json.dumps({"ok": False, "error": "only the funder may cancel their grant"})
        if len(record.get("applications", [])) > 0:
            return json.dumps({"ok": False, "error": "cannot cancel once there are applications"})

        record["status"] = CANCELLED
        record["awarded_at"] = _now_iso()
        self.items[gid] = json.dumps(record)
        _pay(record["funder"], int(record["reward"]))  # return the escrow
        return json.dumps({"ok": True, "id": gid, "status": CANCELLED, "refunded": record["reward"]})

    @gl.public.write
    def review(self, grant_id: str, app_index: str) -> str:
        """Review one application against the grant's criteria; the first MET is paid the escrow. Open to anybody.

        The delivery is fetched inside the round; nobody passes in the verdict. A MET verdict,
        while the grant is still open, awards and pays the escrow to that applicant, exactly once.
        """
        gid = str(grant_id).strip()
        idx = _whole(app_index)
        stored = self.items.get(gid, None)
        if stored is None:
            return json.dumps({"ok": False, "error": "no grant with that id"})
        record = json.loads(stored)
        if record["status"] != OPEN:
            return json.dumps({"ok": False, "error": "this grant is already " + record["status"].lower(),
                               "status": record["status"]})
        apps = list(record.get("applications", []))
        if idx < 0 or idx >= len(apps):
            return json.dumps({"ok": False, "error": "no application with that index"})
        app = apps[idx]
        if app["status"] != PENDING:
            return json.dumps({"ok": False, "error": "this application is already " + app["status"].lower()})

        # Copy into locals before the round. Nothing inside the block reads self
        # and nothing inside it raises.
        title = record["title"]
        criteria = record["criteria"]
        url = app["delivery_url"]

        def look() -> str:
            page = ""
            try:
                got = gl.nondet.web.render(url)
                page = got if isinstance(got, str) else getattr(got, "body", "")
                if isinstance(page, (bytes, bytearray)):
                    page = page.decode("utf-8", "replace")
                page = _clip(str(page), MAX_PAGE)
                if page.strip().lower().startswith(("404: not found", "404 not found", "not found")):
                    page = FETCH_FAILED
            except Exception:
                page = FETCH_FAILED
            if not page or page == FETCH_FAILED:
                return json.dumps({"verdict": UNCLEAR, "quote": "",
                                   "reason": "the delivery page could not be read"})
            try:
                return str(gl.nondet.exec_prompt(_task(title, criteria, page)))
            except Exception as error:
                return json.dumps({"verdict": UNCLEAR, "quote": "",
                                   "reason": _clip("the prompt failed: " + str(error), MAX_REASON)})

        raw = gl.eq_principle.prompt_comparative(
            look,
            principle=(
                f"Both answers must carry the same value in the field named verdict, one of "
                f"{MET}, {UNMET} or {UNCLEAR}. That single field decides whether a grant's reward is "
                "paid to this applicant, so two readers differing on it disagree about whether the "
                "delivery meets the criteria, not about wording. The other fields are not compared, and "
                "the two readers will not have fetched byte-identical copies of the page."
            ),
        )

        verdict = _field(raw, "verdict", VERDICTS, "")
        if not verdict:
            return json.dumps({"ok": False, "error": "the round produced no verdict this contract recognises",
                               "round_said": _clip(str(raw), 400)})

        reason = _text_field(raw, "reason", MAX_REASON)
        quote = _text_field(raw, "quote", MAX_QUOTE)
        outcome = _status_for(verdict)

        # Re-read state: a concurrent review may have awarded the grant while this round ran.
        current = json.loads(self.items[gid])
        if current["status"] != OPEN:
            return json.dumps({"ok": False, "error": "this grant was awarded while the review ran",
                               "status": current["status"]})
        capps = list(current.get("applications", []))
        capp = capps[idx]
        capp["verdict"] = verdict
        capp["reason"] = reason
        capp["quote"] = quote
        current["reviews"] = int(current.get("reviews", 0)) + 1
        awarded = False
        if outcome == WON:
            capp["status"] = WON
            current["status"] = AWARDED
            current["winner"] = capp["applicant"]
            current["winning_app"] = idx
            current["awarded_at"] = _now_iso()
            awarded = True
        elif outcome == REJECTED:
            capp["status"] = REJECTED
        capps[idx] = capp
        current["applications"] = capps
        self.items[gid] = json.dumps(current)
        if awarded:
            _pay(capp["applicant"], int(current["reward"]))  # pay the escrow to the winner, once
        return json.dumps({"ok": True, "grant_id": gid, "application": idx, "verdict": verdict,
                           "status": current["status"], "awarded": awarded, "reason": reason})

    # ------------------------------------------------------------------ reads

    @gl.public.view
    def award(self, grant_id: str) -> str:
        """Who won a grant, the reward paid, and with which delivery."""
        gid = str(grant_id).strip()
        stored = self.items.get(gid, None)
        if stored is None:
            return json.dumps({"exists": False})
        record = json.loads(stored)
        delivery = ""
        wa = int(record.get("winning_app", -1))
        apps = record.get("applications", [])
        if 0 <= wa < len(apps):
            delivery = apps[wa].get("delivery_url", "")
        return json.dumps({"exists": True, "id": gid, "status": record["status"],
                           "winner": record.get("winner", ""), "reward": record["reward"],
                           "delivery_url": delivery})

    @gl.public.view
    def status(self, grant_id: str) -> str:
        """A grant's standing: status, reward, applications and reviews."""
        gid = str(grant_id).strip()
        stored = self.items.get(gid, None)
        if stored is None:
            return json.dumps({"exists": False})
        record = json.loads(stored)
        return json.dumps({"exists": True, "id": gid, "status": record["status"],
                           "reward": record["reward"], "applications": len(record.get("applications", [])),
                           "reviews": record["reviews"], "winner": record.get("winner", "")})

    @gl.public.view
    def get(self, grant_id: str) -> str:
        """The whole grant, including every application and its verdict."""
        gid = str(grant_id).strip()
        stored = self.items.get(gid, None)
        if stored is None:
            return json.dumps({"exists": False})
        return stored

    @gl.public.view
    def size(self) -> str:
        """How many grants are open, awarded and cancelled, and the total escrow awarded."""
        open_n = 0
        awarded = 0
        cancelled = 0
        escrow_open = 0
        awarded_units = 0
        for position in range(len(self.ids)):
            record = json.loads(self.items[self.ids[position]])
            r = int(record["reward"])
            if record["status"] == OPEN:
                open_n += 1
                escrow_open += r
            elif record["status"] == AWARDED:
                awarded += 1
                awarded_units += r
            elif record["status"] == CANCELLED:
                cancelled += 1
        return json.dumps({"total": len(self.ids), "open": open_n, "awarded": awarded,
                           "cancelled": cancelled, "escrow_open": str(escrow_open),
                           "awarded_units": str(awarded_units)})

    @gl.public.view
    def page(self, start: str, count: str) -> str:
        """A slice of the grants, newest first."""
        total = len(self.ids)
        begin = _whole(start)
        want = _whole(count)
        if begin < 0:
            begin = 0
        if want < 1:
            want = 20
        if want > 50:
            want = 50
        out = []
        seen = 0
        position = total - 1 - begin
        while position >= 0 and seen < want:
            record = json.loads(self.items[self.ids[position]])
            record["application_count"] = len(record.get("applications", []))
            record.pop("applications", None)
            out.append(record)
            position -= 1
            seen += 1
        return json.dumps({"total": total, "start": begin, "count": len(out), "items": out})
