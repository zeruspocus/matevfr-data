import unittest

import uk_notams as u


def notam(series, number, code, text, f=None, g=None, d=None, start="2610260000", end="2610302359", kind="N", lower="0", upper="9"):
    extras = (f"<ItemD>{d}</ItemD>" if d else "") + f"<ItemE>{text}</ItemE>" + (f"<ItemF>{f}</ItemF><ItemG>{g}</ItemG>" if f else "")
    return f"""<Notam><NOF>EGGN</NOF><Series>{series}</Series><Number>{number}</Number><Year>26</Year><Type>{kind}</Type>
      <QLine><FIR>EGTT</FIR><Code23>{code}</Code23><Code45>LW</Code45><Lower>{lower}</Lower><Upper>{upper}</Upper></QLine>
      <Coordinates>5230N00153W</Coordinates><Radius>3</Radius><ItemA>EGBB</ItemA>
      <StartValidity>{start}</StartValidity><EndValidity>{end}</EndValidity>{extras}</Notam>"""


PIB = "<Pib><NotamList>" + "".join([
    notam("J", 3377, "RD", "TEMPO DANGER AREA (TDA) EGD289A INSTALLED WI 1.65NM RADIUS OF\n523022N 0015244W (ASTON). MAX HGT 400FT AGL.",
          d="SEP 24-OCT 24 0600-2200"),
    notam("C", 6934, "WP", "DROPPING OF ARTICLES WI 5NM RADIUS OF 503945N 0015237W (3.2NM SE OF BRANKSOME PARK).", f="SFC", g="4700FT AMSL", d="1100-1600"),
    notam("L", 100, "RT", "TEMPORARY RESTRICTED AREA BOUNDED BY 513000N 0010000W 513000N 0000000W 512000N 0000000W 512000N 0010000W", f="SFC", g="FL100", end="PERM"),
    notam("A", 5, "RD", "DANGER AREA EGD123 ACTIVE"),
    notam("V", 32, "RO", "SECURITY - HAZARDOUS SITUATION IN ETHIOPIA. UK OPERATORS ARE ADVISED TO TAKE RISK INTO ACCOUNT WI 5NM RADIUS OF 120000N 0383700E"),
    notam("L", 100, "RT", "THE SAME NOTAM IN ANOTHER SECTION OF THE BULLETIN"),
    notam("B", 7, "OB", "OBST CRANE WI 0.1NM RADIUS OF 523022N 0015244W"),
    notam("D", 9, "RD", "DANGER AREA CANCELLED", kind="C"),
]) + "</NotamList></Pib>"


class UkTests(unittest.TestCase):
    def setUp(self):
        self.result = u.parse(PIB, "2026-10-24T07:00:00Z")
        self.by_id = {f["properties"]["id"]: f for f in self.result["features"]}

    def test_only_areas_with_a_shape_in_their_text_are_kept(self):
        self.assertEqual(set(self.by_id), {"J3377/26", "C6934/26", "L100/26", "V32/26"})
        self.assertEqual(self.result["notamCount"], 6, "a repeated NOTAM is one and a cancellation is not counted")

    def test_danger_area_circle_with_the_height_from_its_text(self):
        p = self.by_id["J3377/26"]["properties"]
        self.assertEqual((p["category"], p["qcode"], p["location"]), ("danger", "QRDLW", "EGBB"))
        self.assertEqual((p["lower"]["text"], p["upper"]["text"], p["upper"]["feet"]), ("SFC", "400 FT AGL", 400))
        self.assertEqual((p["validFrom"], p["validTo"]), ("2026-10-26T00:00:00Z", "2026-10-30T23:59:00Z"))
        self.assertEqual(p["schedule"], "SEP 24-OCT 24 0600-2200")
        ring = self.by_id["J3377/26"]["geometry"]["coordinates"][0]
        self.assertEqual(ring[0], ring[-1])
        lat = sum(q[1] for q in ring[:-1]) / (len(ring) - 1)
        self.assertAlmostEqual(lat, 52 + 30 / 60 + 22 / 3600, places=3)

    def test_a_security_advice_is_a_warning_not_a_restriction(self):
        self.assertEqual(self.by_id["V32/26"]["properties"]["category"], "advisory")

    def test_parachute_area_uses_items_f_and_g(self):
        p = self.by_id["C6934/26"]["properties"]
        self.assertEqual(p["category"], "parachute")
        self.assertEqual((p["lower"]["feet"], p["upper"]["feet"], p["upper"]["reference"]), (0, 4700, "AMSL"))

    def test_polygon_and_permanent(self):
        feature = self.by_id["L100/26"]
        self.assertTrue(feature["properties"]["permanent"])
        self.assertIsNone(feature["properties"]["validTo"])
        self.assertEqual(len(feature["geometry"]["coordinates"][0]), 5)
        self.assertEqual(feature["properties"]["upper"]["text"], "FL100")

    def test_q_line_levels_when_no_limits_are_written(self):
        lower, upper = u.flight_level("0"), u.flight_level("47")
        self.assertEqual((lower["feet"], upper["feet"], upper["text"]), (0, 4700, "FL047"))


if __name__ == "__main__":
    unittest.main()
