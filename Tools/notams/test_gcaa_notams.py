import unittest

import gcaa_notams as g

SAMPLE = """
A3378/26
NOTAMN
Q)OMAE/QRTCA/IV/BO/W/000/020/2537N05540E024
A)OMAE
B)2610230030
C)2610301430
D)0030-1430
E)TEMPO RESTRICTED AREA ESTABLISHED
IN AREA BOUNDED BY LINES JOINING:
255303.07N 0560050.09E
255253.00N 0560105.01E
254602.86N 0555522.19E
254612.73N 0555507.61E
255303.07N 0560050.09E
TFC LANDING OR TAKING OFF FROM INTL
AIRPORTS ARE EXEMPTED.
F)SFC
G)2,000 FT AMSL
A3362/26
NOTAMN
Q)OMAE/QRACA/IV/NBO/AW/000/015/2425N05426E001
A)OMAD
B)2611020400
C)2611051400
D)0400-1400
E)TRA ESTABLISHED IN AREA CIRCLE WITH
RADIUS 1000 M CENTERED ON PSN 242506.6N
0542608.4E
F)SFC
G)1,500 FT AMSL
A3370/26
NOTAMN
Q)OMAE/QRDCA/IV/BO/W/000/050/2432N05509E005
A)OMAE
B)2610260900
C)2610291500
E)DNG AREA OMD 24 ACT
F)SFC
G)5,000 FT AMSL
A2488/26
NOTAMN
Q)OMAE/QOBCE/IV/M/AE/000/002/2452N05508E001
A)OMDW
B)2608070001
C)2611042359
E)OBST CRANE ELEV 53 M AMSL ERECTED
AT VCY OF PSN 245223.92N 0550851.43E
F)SFC
G)174 FT AMSL
"""


class ParserTests(unittest.TestCase):
    def setUp(self):
        self.result = g.parse(SAMPLE, "2026-10-23T23:28:22Z")
        self.by_id = {f["properties"]["id"]: f for f in self.result["features"]}

    def test_only_areas_with_a_shape_are_kept(self):
        self.assertEqual(set(self.by_id), {"A3378/26", "A3362/26"})

    def test_temporary_restricted_area(self):
        feature = self.by_id["A3378/26"]
        p = feature["properties"]
        self.assertEqual(p["category"], "tempRestricted")
        self.assertEqual(p["upper"], {"text": "2,000 FT AMSL", "feet": 2000, "reference": "AMSL"})
        self.assertEqual(p["lower"]["feet"], 0)
        self.assertEqual((p["validFrom"], p["validTo"]), ("2026-10-23T00:30:00Z", "2026-10-30T14:30:00Z"))
        self.assertEqual(p["schedule"], "0030-1430")
        ring = feature["geometry"]["coordinates"][0]
        self.assertEqual(ring[0], ring[-1])
        self.assertAlmostEqual(ring[0][0], 56.013914, places=5)
        self.assertAlmostEqual(ring[0][1], 25.884186, places=5)

    def test_circle_split_over_two_lines(self):
        ring = self.by_id["A3362/26"]["geometry"]["coordinates"][0]
        self.assertEqual(ring[0], ring[-1])
        lon = sum(p[0] for p in ring[:-1]) / (len(ring) - 1)
        lat = sum(p[1] for p in ring[:-1]) / (len(ring) - 1)
        self.assertAlmostEqual(lat, 24 + 25 / 60 + 6.6 / 3600, places=3)
        self.assertAlmostEqual(lon, 54 + 26 / 60 + 8.4 / 3600, places=3)

    def test_limits(self):
        self.assertEqual(g.limit("FL250")["feet"], 25000)
        self.assertEqual(g.limit("820 FT AGL")["reference"], "AGL")
        self.assertEqual(g.limit("GND")["feet"], 0)


if __name__ == "__main__":
    unittest.main()
