import unittest
from ar_supplements import parse, parse_date, kind_of

PAGE = '''
<tr class="vigente"><td>si</td><td id="nroanno">A 257/26</td><td id="title">
<a href="/descarga/sup-6aec7de82bdb3" target="_blank">AD SAN FERNANDO (FDO/SADF) - NOVEDADES TEMPORALES EN AD: RWY 05 IFP SUSPENDIDOS (ESP/ENG) - TEMP -
</a></td><td id="from">05-Nov-26</td></tr>
<tr class="vigente"><td>si</td><td id="nroanno">A 258/26</td><td id="title">
<a href="/descarga/sup-6aecc454e86ca" target="_blank">AFECTACI&Oacute;N DEL ESPACIO A&Eacute;REO &ndash; VISITA / AIRSPACE IMPACT (ESP/ENG) - TEMP -
</a></td><td id="from">05-Nov-26</td></tr>
<tr class=""><td>no</td><td id="nroanno">A 100/26</td><td id="title">
<a href="/descarga/sup-aaaa" target="_blank">AD EZEIZA (EZE/SAEZ) - VIEJO</a></td><td id="from">01-Jan-26</td></tr>
'''

class SupplementsTests(unittest.TestCase):
    def test_only_the_ones_in_force_are_kept(self):
        self.assertEqual([s["id"] for s in parse(PAGE)], ["A 257/26", "A 258/26"])
        self.assertEqual(len(parse(PAGE, only_in_force=False)), 3)

    def test_fields(self):
        s = parse(PAGE)[0]
        self.assertEqual(s["codes"], ["SADF"])
        self.assertEqual(s["kind"], "aerodrome")
        self.assertEqual(s["published"], "2026-11-05")
        self.assertEqual(s["pdf"], "https://ais.anac.gob.ar/descarga/sup-6aec7de82bdb3")

    def test_html_entities_and_airspace_kind(self):
        s = parse(PAGE)[1]
        self.assertIn("AFECTACIÓN DEL ESPACIO AÉREO – VISITA", s["title"])
        self.assertEqual(s["kind"], "airspace")

    def test_dates(self):
        self.assertEqual(parse_date("07-Nov-26"), "2026-11-07")
        self.assertIsNone(parse_date("nope"))

    def test_kind_of_publication_change(self):
        self.assertEqual(kind_of("MODIFICACIONES EN LA AIP PARTE ENR 3.1 - AWY W72"), "publication")

if __name__ == "__main__":
    unittest.main()
