"""v5.10 — logo MAM (en-tête, rapports) et plusieurs destinataires."""
from utils import brand as B
from utils.alerts import parse_recipients


def test_logo_assets_present():
    for p in (B.MARK_SVG, B.MARK_PNG, B.LOGO_PNG, B.BANNER_PNG, B.FAVICON):
        assert p.exists(), p
    svg = B.mark_svg_inline(40)
    assert svg.startswith("<svg") and 'width="40"' in svg and "\n" not in svg
    assert B.mark_svg_inline(40) != svg                          # identifiants de dégradé uniques


def test_parse_recipients():
    assert parse_recipients("a@x.com, b@y.fr; c@z.com\nA@x.com pas-une-adresse") == ["a@x.com", "b@y.fr", "c@z.com"]
    assert parse_recipients("") == [] and parse_recipients(["d@e.com"]) == ["d@e.com"]


def test_send_email_to_several(monkeypatch):
    import smtplib
    from utils import alerts as AL
    sent = {}

    class FakeSMTP:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def ehlo(self): pass
        def starttls(self, **k): pass
        def has_extn(self, n): return True
        def login(self, u, p): sent["login"] = u
        def send_message(self, msg, to_addrs=None): sent["to"], sent["hdr"] = to_addrs, msg["To"]

    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    for k, v in dict(SMTP_HOST="smtp.gmail.com", SMTP_PORT="587", SMTP_USER="mam@gmail.com",
                     SMTP_PASSWORD="abcdefghijklmnop", SMTP_SECURITY="starttls").items():
        monkeypatch.setenv(k, v)
    err = AL.send_email("a@x.com, b@y.com;c@z.com", "Test", "<b>ok</b>")
    assert err is None and sent["to"] == ["a@x.com", "b@y.com", "c@z.com"]
    assert sent["hdr"] == "a@x.com, b@y.com, c@z.com"
    assert AL.send_email("pas une adresse", "Test", "x").startswith("Aucune adresse")


def test_reports_carry_logo():
    from utils.reporting import make_pdf
    pdf = make_pdf("Titre", "Sous-titre", [("p", "Bonjour")])
    assert pdf[:4] == b"%PDF" and b"/Image" in pdf
