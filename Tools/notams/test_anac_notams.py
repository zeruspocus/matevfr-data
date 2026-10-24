import unittest

import anac_notams as a


def row(number, place, code, start, end, english, spanish="TEXTO"):
    return f"""
    <tr>
      <td id="place"><p>{number}</p><p>{place}</p><p>({code})</p></td>
      <td id="info"><p>Desde: {start}</p><p>Hasta: {end}                    </p>
        <p>{english}<span id="versionbreak">Versión en Español:</span> {spanish}</p></td>
    </tr>"""


PAGE = "<table>" + row(
    "A3115/2026", "AVISOS FIR EZEIZA", "-EF", "2026-08-07 10:45:00", "2026-11-04 22:35:00",
    "PJE WILL TAKE PLACE IN AD VEDIA -BUENOS AIRES- COORD GEO 342910S/0612923W, RDO 3NM. AFFECTS AWY W9 "
    "D)WED, FRI, SAT AND SUN SR-SS F)GND G)FL120 WED, FRI, SAT AND SUN SR-SS", "PJE SE REALIZARA EN AD VEDIA"
) + row(
    "A4375/2026", "AVISOS FIR CORDOBA", "-CF", "2026-10-26 10:00:00", "2026-10-27 23:00:00",
    "AREA PROHIBITED IN SANTA CATALINA - CORDOBA- COORD GEO 331013S/0642528W 331011S/0642527W 331008S/0642521W "
    "331019S/0642530W AFFECTS CTR AND TMA RIO CUARTO F) GND G) FL090) DLY 1000-1115 AND 2030-2300"
) + row(
    "A4407/2026", "AVISOS FIR EZEIZA", "-EF", "2026-11-07 11:00:00", "2026-11-07 17:00:00",
    "TEMPO RESTRICTED AREA ACT SECURITY OPERATION IN COLON COORD GEO FM 323042S/0581548W NORTHWARD FOLLOWING AN ARC "
    "WITH A RDO 14 NM WITH CENTER IN COORD GEO 321602S/0581600W"
) + row(
    "A1544/2026", "AVISOS A TODAS LAS FIRS", "---", "2026-08-12 19:16:00", "Perm",
    "DUE TO SUP AIP A 209/2026 TEMPORARY CHANGES IN AIP PART AD"
) + row(
    "A4305/2026", "AVISOS FIR CORDOBA", "-CF", "2026-10-26 11:30:00", "2026-10-30 20:00:00",
    "TEMPO RESTRICTED AREA ACT IN RIO CUARTO E COORD GEO 314658S0650741W, 314053S0645051W, 314210S0640401W, "
    "ENDING 314658S0650741W. AFFECTS SECT S CORDOBA CTA FL285 FL415 DLY 1130-1330"
) + "</table>"


class AnacTests(unittest.TestCase):
    def setUp(self):
        self.result = a.parse([PAGE, PAGE], "2026-10-24T07:00:00Z")
        self.by_id = {f["properties"]["id"]: f for f in self.result["features"]}

    def test_counts_every_notam_once_and_draws_only_the_areas(self):
        self.assertEqual(self.result["notamCount"], 5, "the same NOTAM in two lists is one")
        self.assertEqual(set(self.by_id), {"A3115/2026", "A4375/2026", "A4305/2026"}, "an arc and a notice without coordinates are not drawn")

    def test_parachute_circle(self):
        feature = self.by_id["A3115/2026"]
        p = feature["properties"]
        self.assertEqual(p["category"], "parachute")
        self.assertEqual((p["lower"]["text"], p["upper"]["text"]), ("GND", "FL120"))
        self.assertEqual(p["validFrom"], "2026-08-07T10:45:00Z")
        self.assertTrue(p["schedule"].startswith("WED, FRI, SAT AND SUN SR-SS"))
        ring = feature["geometry"]["coordinates"][0]
        lat = sum(q[1] for q in ring[:-1]) / (len(ring) - 1)
        self.assertAlmostEqual(lat, -(34 + 29 / 60 + 10 / 3600), places=3)
        self.assertEqual(p["textEs"], "PJE SE REALIZARA EN AD VEDIA")

    def test_prohibited_polygon_with_a_daily_schedule(self):
        p = self.by_id["A4375/2026"]["properties"]
        self.assertEqual(p["category"], "prohibited")
        self.assertEqual(p["upper"]["feet"], 9000)
        self.assertEqual(p["schedule"], "DLY 1000-1115 AND 2030-2300")
        self.assertEqual(len(self.by_id["A4375/2026"]["geometry"]["coordinates"][0]), 5)

    def test_limits_without_f_and_g_and_coordinates_without_a_slash(self):
        feature = self.by_id["A4305/2026"]
        self.assertEqual((feature["properties"]["lower"]["feet"], feature["properties"]["upper"]["feet"]), (28500, 41500))
        self.assertAlmostEqual(feature["geometry"]["coordinates"][0][0][1], -(31 + 46 / 60 + 58 / 3600), places=3)

    def test_a_missing_sign_typo_and_permanent(self):
        self.assertEqual(a.points("261217S-0544537W"), [(round(-(54 + 45 / 60 + 37 / 3600), 6), round(-(26 + 12 / 60 + 17 / 3600), 6))])


if __name__ == "__main__":
    unittest.main()
