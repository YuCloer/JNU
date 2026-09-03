import unittest

from app.scouting import ability_profile, recommend_xi


class ScoutingTests(unittest.TestCase):
    def test_official_reference_is_preserved(self):
        profile = ability_profile({"id": "mbappe", "name": "Kylian Mbappé", "position": "ST", "age": 27})
        self.assertEqual(profile["overall"], 91)
        self.assertTrue(profile["ability_is_reference"])
        self.assertEqual(profile["attributes"]["pace"], 97)

    def test_baseline_never_falls_below_academy_floor(self):
        profile = ability_profile({"id": "academy-1", "name": "Academy Player", "position": "CB", "age": 17})
        self.assertGreaterEqual(profile["overall"], 60)
        self.assertFalse(profile["ability_is_reference"])
        self.assertTrue(all(value >= 60 for value in profile["attributes"].values()))

    def test_recommendation_keeps_goalkeeper_in_goal(self):
        players = [
            {"id": "gk", "name": "Goalkeeper", "position": "GK", "overall": 70},
            {"id": "cb", "name": "Centre Back", "position": "CB", "overall": 75},
        ]
        zones = [
            {"role": "GK", "x": .5, "y": .9, "allow": ["GK"]},
            {"role": "CB", "x": .5, "y": .7, "allow": ["CB"]},
        ]
        view = recommend_xi(players, zones, "test")
        self.assertEqual(view["slots"][0]["player_id"], "gk")
        self.assertEqual(view["slots"][0]["tactical_role"], "GK")


if __name__ == "__main__":
    unittest.main()
