import hashlib
import hmac

from app import config, payments
from app.data import find_skills, normalize, tier
from app.extract import course_skills, grounded
from app.scoring import gaps, readiness

MARKET = {"sample_size": 10, "skills": {
    "docker": {"frequency": 0.8, "tier": "must", "links": []},
    "python": {"frequency": 0.6, "tier": "must", "links": []},
    "redis": {"frequency": 0.4, "tier": "nice", "links": []},
    "kubernetes": {"frequency": 0.1, "tier": "rare", "links": []},  # ignored
}}


def e(level, confirmed=None, source="cv"):
    return {"level": level, "evidence": [{"source": source, "text": "x"}], "confirmed": confirmed}


def test_readiness_formula():
    # total = 0.8 + 0.6 + 0.4 = 1.8 ; got = 0.6*1 + 0.4*0.5 = 0.8 -> 44.4 -> 44
    profile = {"python": e("intermediate"), "redis": e("basic", source="course"), "kubernetes": e("strong")}
    assert readiness(profile, MARKET) == 44


def test_readiness_bounds_and_confirmation():
    assert readiness({}, MARKET) == 0
    full = {s: e("strong") for s in ("docker", "python", "redis")}
    assert readiness(full, MARKET) == 100
    assert readiness({"docker": e("none", confirmed=True)}, MARKET) == 44   # confirmed counts as 1.0
    assert readiness({"docker": e("strong", confirmed=False)}, MARKET) == 0  # user denied
    assert readiness({}, {"sample_size": 0, "skills": {}}) == 0


def test_readiness_deterministic():
    profile = {"python": e("basic")}
    assert len({readiness(profile, MARKET) for _ in range(20)}) == 1


def test_gaps_ranking_and_reasons():
    profile = {"python": e("intermediate"), "redis": e("basic", source="course")}
    g = gaps(profile, MARKET)
    assert [x["skill_id"] for x in g] == ["docker", "redis"]  # python matched, kubernetes is rare
    assert g[0]["reason"] == "Not found in your CV or courses" and g[0]["user_level"] == "none"
    assert g[1]["reason"] == "Only seen in a course, no project" and g[1]["user_level"] == "basic"


def test_tiers():
    assert (tier(0.5), tier(0.49), tier(0.2), tier(0.19)) == ("must", "nice", "nice", "rare")


def test_normalize():
    assert normalize("Docker Compose") == "docker"
    assert normalize("  PostgreSQL ") == "sql"
    assert normalize("k8s") == "kubernetes"
    assert normalize("database_design") == "database_design"
    assert normalize("C#") == "csharp"
    assert normalize("cobol") is None


def test_find_skills_word_boundaries():
    assert "java" not in find_skills("JavaScript developer")
    assert {"javascript", "react"} <= find_skills("JavaScript and React.js")
    assert "ci_cd" in find_skills("CI/CD with Jenkins")
    assert "machine_learning" not in find_skills("HTML templates")


def test_course_map():
    p = course_skills("CS305 Database Systems   A\nCS201 Object Oriented Programming (Java)")
    assert p["sql"]["level"] == "basic" and p["sql"]["evidence"][0]["source"] == "course"
    assert {"java", "oop", "database_design"} <= p.keys()


def test_grounding():
    cv = "Built a REST API in Python using FastAPI for clinic booking."
    assert grounded("built a REST API in python using FastAPI", cv)
    assert not grounded("Deployed Kubernetes clusters on AWS", cv)


def test_paymob_hmac(monkeypatch):
    monkeypatch.setattr(config, "PAYMOB_HMAC_SECRET", "secret")
    obj = {"amount_cents": 9900, "created_at": "2026-10-24T10:00:00", "currency": "EGP", "error_occured": False,
           "has_parent_transaction": False, "id": 123, "integration_id": 456, "is_3d_secure": True,
           "is_auth": False, "is_capture": False, "is_refunded": False, "is_standalone_payment": True,
           "is_voided": False, "order": {"id": 789, "merchant_order_id": "abc-1"}, "owner": 1, "pending": False,
           "source_data": {"pan": "2346", "sub_type": "MasterCard", "type": "card"}, "success": True}
    msg = "9900" "2026-10-24T10:00:00" "EGP" "false" "false" "123" "456" "true" "false" "false" "false" "true" \
          "false" "789" "1" "false" "2346" "MasterCard" "card" "true"
    good = hmac.new(b"secret", msg.encode(), hashlib.sha512).hexdigest()
    assert payments.verify_transaction(obj, good)
    assert not payments.verify_transaction({**obj, "amount_cents": 1}, good)
    assert not payments.verify_transaction(obj, "bad")
    flat = {k: payments._s(payments._dig(obj, k)) for k in payments.HMAC_FIELDS if k != "order.id"}
    assert payments.verify_redirect({**flat, "order": "789", "hmac": good})
    assert payments.outcome(True, False) == "paid" and payments.outcome("false", "false") == "failed"
    assert payments.analysis_id_from_reference("abc123-1700000000") == "abc123"
