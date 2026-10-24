import unittest

import us_tfr as t

POINTS = [("31.15007463N", "088.89166667W"), ("31.14956692N", "088.88492141W"), ("31.11000000N", "088.88000000W"),
          ("31.10000000N", "088.90000000W"), ("31.15007463N", "088.89166667W")]
VERTICES = "".join(f"<Avx><codeDatum>WGE</codeDatum><codeType>GRC</codeType><geoLat>{a}</geoLat><geoLong>{b}</geoLong></Avx>" for a, b in POINTS)


def tfr(number="6/2017", groups=1):
    one = f"""
    <TFRAreaGroup>
      <aseTFRArea>
        <txtName>Hazard Area{{n}}</txtName>
        <codeDistVerUpper>ALT</codeDistVerUpper><valDistVerUpper>2000</valDistVerUpper><uomDistVerUpper>FT</uomDistVerUpper>
        <codeDistVerLower>ALT</codeDistVerLower><valDistVerLower>0</valDistVerLower><uomDistVerLower>FT</uomDistVerLower>
        <ScheduleGroup><startTime>2026-10-23T12:00:00</startTime><endTime>2026-10-23T23:00:00</endTime></ScheduleGroup>
      </aseTFRArea>
      <abdMergedArea>{VERTICES}</abdMergedArea>
    </TFRAreaGroup>"""
    return f"""<?xml version="1.0"?><XNOTAM-Update><Group><Add><Not>
      <NotUid><txtLocalName>{number}</txtLocalName></NotUid>
      <dateEffective>2026-10-24T12:00:00</dateEffective><dateExpire>2026-10-27T23:00:00</dateExpire>
      <TfrNot>{''.join(one.replace('{n}', str(i + 1)) for i in range(groups))}</TfrNot>
      <txtDescrUSNS>!FDC 6/2017 ZHU MS..TEMPORARY FLIGHT RESTRICTIONS. SFC-2000FT</txtDescrUSNS>
    </Not></Add></Group></XNOTAM-Update>"""


class TfrTests(unittest.TestCase):
    META = {"notam_id": "6/2017", "state": "MS", "type": "HAZARDS"}

    def test_a_tfr_becomes_an_area_with_limits_dates_and_schedule(self):
        feature = t.parse_one(tfr(), self.META)[0]
        p = feature["properties"]
        self.assertEqual((p["id"], p["category"], p["location"]), ("6/2017", "tfr", "MS · HAZARDS"))
        self.assertEqual((p["lower"]["text"], p["upper"]["text"], p["upper"]["feet"]), ("SFC", "2000 FT AMSL", 2000))
        self.assertEqual((p["validFrom"], p["validTo"]), ("2026-10-24T12:00:00Z", "2026-10-27T23:00:00Z"))
        self.assertEqual(p["schedule"], "DLY 1200-2300 UTC")
        ring = feature["geometry"]["coordinates"][0]
        self.assertEqual(ring[0], ring[-1])
        self.assertEqual(tuple(ring[0]), (-88.891667, 31.150075))

    def test_several_areas_of_one_tfr_are_told_apart(self):
        ids = [f["properties"]["id"] for f in t.parse_one(tfr(groups=2), self.META)]
        self.assertEqual(ids, ["6/2017 Hazard Area1", "6/2017 Hazard Area2"])

    def test_heights_in_flight_levels_and_above_ground(self):
        import xml.etree.ElementTree as ET
        area = ET.fromstring("<a><codeDistVerUpper>STD</codeDistVerUpper><valDistVerUpper>180</valDistVerUpper><uomDistVerUpper>FL</uomDistVerUpper>"
                             "<codeDistVerLower>HEI</codeDistVerLower><valDistVerLower>400</valDistVerLower><uomDistVerLower>FT</uomDistVerLower></a>")
        self.assertEqual(t.limit(area, "Upper")["text"], "FL180")
        self.assertEqual(t.limit(area, "Lower"), {"text": "400 FT AGL", "feet": 400, "reference": "AGL"})

    def test_the_list_drives_the_file(self):
        result = t.parse([{"notam_id": "6/2017", "state": "MS", "type": "HAZARDS"}, {"notam_id": "6/9999", "state": "TX", "type": "VIP"}],
                         {"6_2017": tfr()}, "2026-10-24T00:00:00Z")
        self.assertEqual(result["notamCount"], 2)
        self.assertEqual(len(result["features"]), 1, "a TFR whose detail could not be read is left out, not a reason to stop")


if __name__ == "__main__":
    unittest.main()
